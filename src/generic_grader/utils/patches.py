import builtins
import importlib
import os
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from freezegun import freeze_time

from generic_grader.utils.exceptions import (
    DisallowedFileAccessError,
    DisallowedFunctionCallError,
    DisallowedImportError,
    ExitError,
    QuitError,
    TurtleDoneError,
    TurtleWriteError,
)
from generic_grader.utils.mocks import (
    make_mock_function_noop,
    make_mock_function_raise_error,
)
from generic_grader.utils.options import Options
from generic_grader.utils.resource_limits import memory_limit, time_limit

# ---------------------------------------------------------------------------
# Security: Layer 1 — in-process import blocklist, dangerous-attr patches,
# and a sandboxed open().  See issue #98.  This is defense in depth; full
# isolation requires a separate process / sandbox (tracked in #98 follow-up).
# ---------------------------------------------------------------------------

BLOCKED_MODULES = frozenset(
    {
        # Subprocess / shell
        "subprocess",
        "pty",
        # Network
        "socket",
        "socketserver",
        "ssl",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "urllib.error",
        "http",
        "http.client",
        "http.server",
        "requests",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "nntplib",
        "xmlrpc",
        "xmlrpc.client",
        "xmlrpc.server",
        # Native / FFI / process
        "ctypes",
        "ctypes.util",
        "cffi",
        "multiprocessing",
        "_multiprocessing",
        # Misc dangerous
        "webbrowser",
    }
)

# Specific dangerous attributes on modules students legitimately need.
_DANGEROUS_ATTRS = (
    # os: shell and process management
    "os.system",
    "os.popen",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.fork",
    "os.forkpty",
    "os.kill",
    "os.killpg",
    # os: destructive filesystem ops
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.removedirs",
    # shutil: destructive
    "shutil.rmtree",
    "shutil.move",
    # signal: would let students disarm our SIGALRM-based time limit
    "signal.signal",
    "signal.alarm",
    "signal.setitimer",
    # resource: would let students raise the memory limit
    "resource.setrlimit",
    "resource.prlimit",
    # sys: tracing/profiling can be abused to escape patches
    "sys.settrace",
    "sys.setprofile",
)


# Paths the sandboxed open() refuses by default.  These cover the most
# common exfiltration / grade-tampering targets on Gradescope.
_DEFAULT_PROTECTED_DIRS = (
    "tests",  # contains reference.py, expected_output, configs
    "/autograder/source/tests",
    "/autograder/results",
)
_DEFAULT_PROTECTED_FILES = (
    "results.json",
    "/autograder/results/results.json",
)


def _module_is_blocked(name, blocked):
    """Return True if `name` (or any parent package) is in `blocked`."""
    parts = name.split(".")
    for i in range(len(parts)):
        prefix = ".".join(parts[: i + 1])
        if prefix in blocked:
            return True
    return False


def make_import_blocklist_patches(extra_blocked=()):
    """Block dangerous imports at both `builtins.__import__` and
    `importlib.import_module`.

    `extra_blocked` lets a caller (or test) add additional module names.
    """
    blocked = frozenset(BLOCKED_MODULES | set(extra_blocked))
    real_import = builtins.__import__
    real_import_module = importlib.import_module

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if _module_is_blocked(name, blocked):
            raise DisallowedImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    def safe_import_module(name, package=None):
        resolved = name
        if package and name.startswith("."):
            # Resolve relative imports to absolute names before checking.
            resolved = importlib.util.resolve_name(name, package)
        if _module_is_blocked(resolved, blocked):
            raise DisallowedImportError(resolved)
        return real_import_module(name, package)

    return [
        {"args": ("builtins.__import__", safe_import)},
        {"args": ("importlib.import_module", safe_import_module)},
    ]


def make_dangerous_attr_patches():
    """Patch dangerous attributes on otherwise-allowed modules so calls raise
    `DisallowedFunctionCallError`.

    `create=True` keeps the patch usable on attributes that may not exist on
    all platforms (e.g. `os.fork` is POSIX-only).
    """

    def make(target):
        def blocked(*args, **kwargs):
            raise DisallowedFunctionCallError(target)

        return {"args": (target, blocked), "kwargs": {"create": True}}

    return [make(t) for t in _DANGEROUS_ATTRS]


def _resolve(path_like):
    """Resolve a path-like to an absolute string without requiring it to exist."""
    try:
        return os.path.realpath(os.fspath(path_like))
    except TypeError:
        # File descriptors / other non-path arguments: not a path we can check.
        return None


def make_open_sandbox_patch(extra_allowed=(), extra_blocked=()):
    """Patch `builtins.open` to refuse reads/writes on grader-internal files.

    The block list covers the test fixtures, the grader package itself, and
    common Gradescope result paths.  Files inside the student's current
    working directory remain accessible (excluding any explicitly protected
    subdirectory such as `tests/`).

    Callers can extend either list:
      - `extra_allowed`: explicit file paths or directories to permit.
      - `extra_blocked`: extra paths to forbid.
    """
    real_open = builtins.open

    # Resolve grader package install path once (covers both editable and
    # site-packages installs).
    import generic_grader  # local import to avoid a cycle at module load

    grader_pkg_dir = os.path.realpath(os.path.dirname(generic_grader.__file__))

    allowed = {os.path.realpath(p) for p in extra_allowed}
    extra_blocked_resolved = {os.path.realpath(p) for p in extra_blocked}

    def _is_inside(path, directory):
        try:
            return os.path.commonpath([path, directory]) == directory
        except ValueError:
            # Different drives on Windows etc.
            return False

    def sandboxed_open(file, *args, **kwargs):
        resolved = _resolve(file)
        if resolved is None:
            # e.g. an int file descriptor — let the real open handle it.
            return real_open(file, *args, **kwargs)

        # Explicit user-supplied allow list wins.
        if resolved in allowed:
            return real_open(file, *args, **kwargs)
        for path in allowed:
            if _is_inside(resolved, path):
                return real_open(file, *args, **kwargs)

        # Hard blocks: grader package internals.
        if _is_inside(resolved, grader_pkg_dir):
            raise DisallowedFileAccessError(str(file))

        # Caller-supplied extra blocks.
        if resolved in extra_blocked_resolved:
            raise DisallowedFileAccessError(str(file))

        # Default protected files (e.g. results.json).
        basename = os.path.basename(resolved)
        if basename in _DEFAULT_PROTECTED_FILES or resolved in {
            os.path.realpath(p) for p in _DEFAULT_PROTECTED_FILES
        }:
            raise DisallowedFileAccessError(str(file))

        # Default protected directories (e.g. tests/, /autograder/results).
        for prot in _DEFAULT_PROTECTED_DIRS:
            prot_abs = os.path.realpath(prot)
            if os.path.isdir(prot_abs) and _is_inside(resolved, prot_abs):
                raise DisallowedFileAccessError(str(file))

        return real_open(file, *args, **kwargs)

    return {"args": ("builtins.open", sandboxed_open)}


def make_security_patches(o: Options):
    """Bundle all Layer-1 security patches based on `o`.

    Returns an empty list when `o.disable_security_patches` is True so that
    legacy assignments which require e.g. `socket` can opt out.
    """
    if getattr(o, "disable_security_patches", False):
        return []
    patches = []
    patches.extend(make_import_blocklist_patches())
    patches.extend(make_dangerous_attr_patches())
    patches.append(make_open_sandbox_patch())
    return patches


def make_turtle_done_patches(modules):
    """
    Patch extra calls to done()/mainloop().

    This prevents hangs when the student mistakenly calls one of them.  The `modules`
    parameter should be a list or tuple of the assignment's module names.  E.g.
    `modules = ["vowels", "random_vowels"]`.
    """
    return [
        {
            "args": make_mock_function_raise_error(f"{module}.{func}", TurtleDoneError),
            "kwargs": {"create": True},
        }
        for func in ["done", "mainloop"]
        for module in ["turtle", *modules]
    ]


def make_turtle_write_patches(modules):
    """
    Make patches to block access to `turtle.write`.

    The `modules` parameter should be a list or tuple of the assignment's module names.
    E.g. `modules = ["vowels", "random_vowels"]`.
    """
    return [
        {
            "args": make_mock_function_raise_error(f"{module}.write", TurtleWriteError),
            "kwargs": {"create": True},
        }
        for module in ["turtle", *modules]
    ]


def make_pyplot_noop_patches(modules):
    """Patch `matplotlib.pyplt.show` with a noop."""
    return [
        {
            "args": make_mock_function_noop(f"{module}.{func}"),
            "kwargs": {"create": True},
        }
        for func in ["savefig", "show"]
        for module in ["matplotlib.pyplot", *modules]
    ]


def make_exit_quit_patches():
    """Patch the builtins exit and quit functions."""
    return [
        {
            "args": make_mock_function_raise_error("builtins.exit", ExitError),
        },
        {"args": make_mock_function_raise_error("builtins.quit", QuitError)},
    ]


@contextmanager
def custom_stack(o: Options):
    """Create a custom stack with resource limits and patches."""
    with ExitStack() as stack:
        # Add custom resource limits
        stack.enter_context(time_limit(o.time_limit))
        stack.enter_context(memory_limit(o.memory_limit_GB))
        if o.fixed_time:
            stack.enter_context(freeze_time(o.fixed_time))

        # Order matters: security patches go first, then exit/quit, then
        # caller-supplied patches.  `mock.patch` is LIFO when stacked, so
        # later entries win — caller patches can override security defaults
        # when explicitly needed (e.g. tests that exercise our own internals).
        patches = (
            make_security_patches(o) + make_exit_quit_patches() + (o.patches or [])
        )
        for p in patches:
            stack.enter_context(
                patch(
                    *p.get("args", ()),  # permit missing args
                    **p.get("kwargs", {}),  # permit missing kwargs
                )
            )

        yield
