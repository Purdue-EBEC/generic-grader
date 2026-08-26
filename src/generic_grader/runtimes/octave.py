"""GNU Octave runtime for generic-grader.

This runtime runs student and reference code written as ``.m`` files
inside GNU Octave via a hardened subprocess.  It is selected by setting
``Options.language = "octave"``.

Design overview
---------------

* **File location.**  ``resolve`` looks for ``<module>.m`` in the
  process's current working directory — the same directory Gradescope
  drops the student submission into, and the same directory the
  existing Python tests already switch to via ``fix_syspath``.  A
  missing file produces the same shape of error the Python runtime
  produces via :class:`Importer`: ``test.fail("Unable to import ...")``
  with a hint pointing at the expected filename.

* **Script vs. function.**  MATLAB / Octave ``.m`` files come in two
  flavours.  The test author signals which shape they want by whether
  they supply ``options.args`` / ``options.kwargs``:

  * *Script mode* (no args, no kwargs).  The file is run top-to-bottom
    — Octave executes ``<stem>`` where ``<stem>`` is the basename of
    the resolved ``.m`` file.  Reference and student files typically
    live under different stems (e.g. ``main.m`` vs ``ref_main.m``),
    so we deliberately do *not* require the two to share a stem —
    each side runs its own file.

  * *Function mode* (any args or kwargs supplied).  We call
    ``<obj_name>(<args>)`` and the file must define a function of
    that name — either as the top-of-file function of ``<stem>.m``
    or as a local/nested function inside it.  In this case
    ``obj_name`` is shared across the reference and student runs so
    the test contract is the same for both.

  This mirrors what the Python runtime does implicitly — a Python
  ``main()`` test both runs top-to-bottom (via ``__import__``) *and*
  invokes a callable.  Octave has to make the choice explicit.

* **Argument passing.**  Positional ``args`` and keyword ``kwargs`` are
  serialized into an Octave expression by :func:`_format_args`.  The
  supported types are Python's basic scalars — ``bool`` (``true`` /
  ``false``), ``int``, ``float`` (special-cased for NaN / +Inf / -Inf),
  and ``str`` (single-quoted with embedded quotes doubled per Octave's
  own rules).  Anything else raises a clear ``TypeError`` at grader
  build time, which is friendlier than an opaque parse error inside
  Octave.  Nested containers are intentionally *not* supported in the
  first pass; a follow-on PR will add them alongside the
  ``function_return_values_match_reference`` test type.

* **Sandboxing.**  The subprocess is launched with a scrubbed
  environment (``PATH``, ``HOME``, ``LANG`` only), ``--no-init-file``
  and ``--norc`` so ``~/.octaverc`` cannot influence the run, and
  POSIX resource limits set in a ``preexec_fn`` derived from the
  ``time_limit`` and ``memory_limit_GB`` fields on ``Options``.
  ``subprocess.communicate(timeout=...)`` provides a wall-clock
  backstop and — on timeout — the process group is killed so any
  child processes die with it.  This is language-independent
  sandboxing, matching the "sandbox independent of backend" design
  the extension was scoped around.

* **stdin (simulated user input).**  Anything in ``options.entries`` is
  joined with newlines and fed to the child process's stdin.  In
  Octave, ``input("prompt")`` reads from ``stdin`` when running in
  non-interactive mode with ``--eval``, which is exactly the mode we
  invoke.
"""

from __future__ import annotations

import math
import os
import resource
import shutil
import signal
import subprocess
import sys
from textwrap import dedent
from unittest import TestCase

from generic_grader.runtimes.base import RuntimeResult
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.options import Options

# Executable name — factored out for tests.  Overriding it lets a live
# integration test skip when Octave isn't installed without special
# casing subprocess.run.
OCTAVE_EXECUTABLE = os.environ.get("OCTAVE_EXECUTABLE", "octave")

# One gigabyte in bytes.  ``options.memory_limit_GB`` is a float number
# of gigabytes; the child's ``RLIMIT_AS`` is set to that many bytes.
_GB = 1024**3


class OctaveNotInstalledError(RuntimeError):
    """Raised when the Octave executable is not on ``PATH``.

    Distinct from a student's own Octave error — this indicates a
    misconfigured grader environment and is surfaced to the test author
    (via ``test.fail``) rather than the student.
    """


class OctaveRuntimeError(RuntimeError):
    """Raised when the Octave process exits with an error.

    Carries the child's captured stderr so ``__User__.call_obj`` can
    include it in the student-facing failure message the same way it
    already includes Python tracebacks.
    """

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


class OctaveTimeoutError(RuntimeError):
    """Raised when the Octave process is killed by the wall-clock
    ``time_limit`` on :class:`Options`.

    Mapped to the same student-facing "took too long" message the
    Python runtime uses via :class:`TimeoutError`.
    """


# ---------------------------------------------------------------------------
# Argument serialization
# ---------------------------------------------------------------------------
def _format_scalar(value) -> str:
    """Render a Python scalar as an Octave expression.

    The switch is deliberately exhaustive on ``type(value)`` rather
    than ``isinstance(...)``.  This means ``True`` isn't accidentally
    treated as ``1`` (Python's ``bool`` is a subclass of ``int``) —
    students should see the distinction faithfully in Octave, and
    tests are cleaner when the mapping is obvious.
    """
    t = type(value)
    if t is bool:
        return "true" if value else "false"
    if t is int:
        return str(value)
    if t is float:
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
        # ``repr`` round-trips floats; Octave accepts the ``e`` form.
        return repr(value)
    if t is str:
        # Octave single-quoted strings escape embedded single quotes by
        # doubling them.  This is enough — single-quoted strings do not
        # interpret backslashes so we don't have to escape those.
        return "'" + value.replace("'", "''") + "'"
    raise TypeError(
        f"Cannot serialize argument of type {t.__name__!r} to Octave. "
        "Only bool, int, float, and str are supported in this release."
    )


def _format_args(args, kwargs) -> str:
    """Produce the parenthesised argument list for an Octave call.

    Octave has no first-class ``**kwargs`` — the closest equivalent is
    passing a trailing sequence of ``('key', value)`` pairs, which
    functions like ``plot`` already use.  We adopt that convention:
    ``kwargs={'linewidth': 2}`` becomes ``, 'linewidth', 2``.  Test
    authors who need MATLAB-style optional arguments therefore get a
    natural mapping; those who don't need kwargs pay nothing.

    If ``args`` and ``kwargs`` are both empty the return value is
    ``""``, so the caller can compose ``obj_name + _format_args(...)``
    for script mode (no parens) as easily as for function mode.
    """
    parts = [_format_scalar(a) for a in args]
    for key, value in kwargs.items():
        parts.append(_format_scalar(str(key)))
        parts.append(_format_scalar(value))
    if not parts:
        return ""
    return "(" + ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
class OctaveRuntime:
    """Runtime that executes ``.m`` files under GNU Octave.

    A single instance is created per ``__User__`` (see
    :mod:`generic_grader.utils.user`); each call to :meth:`run`
    launches a fresh Octave subprocess so there is no state leakage
    between the reference run and the student run.
    """

    name = "Octave"

    # ------------------------------------------------------------------
    # resolve
    # ------------------------------------------------------------------
    def resolve(self, test: TestCase, options: Options, module: str):
        """Verify ``<module>.m`` exists in the current working directory.

        Returns the absolute path to the file as the opaque *handle*
        that :meth:`run` will consume.  On failure we call
        ``test.fail(...)`` with a message shaped like the Python
        runtime's "Unable to import" text, so students see a
        consistent style regardless of language.
        """
        path = os.path.abspath(module + ".m")
        if not os.path.isfile(path):
            wrapper = get_wrapper()
            msg = (
                "\n"
                + wrapper.fill(f"Unable to load `{module}.m`.")
                + "\n\nHint:\n"
                + wrapper.fill(
                    f"Make sure you have submitted a file named `{module}.m` "
                    "in the top level of your submission."
                )
            )
            test.failureException = FileNotFoundError
            test.fail(msg)
        return path

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------
    def run(
        self,
        options: Options,
        handle,
        log,
        entries,
    ) -> RuntimeResult:
        """Invoke the resolved ``.m`` under Octave.

        Writes captured stdout into ``log`` (respecting its optional
        ``log_limit``), pipes ``entries`` to stdin, enforces
        ``time_limit`` / ``memory_limit_GB`` via the preexec hook, and
        raises :class:`OctaveRuntimeError`,
        :class:`OctaveTimeoutError`, or
        :class:`OctaveNotInstalledError` on failure — all three of
        which the caller in :mod:`generic_grader.utils.user` renders
        into student-facing messages.
        """
        # `handle` is the resolved .m path.  We invoke Octave with the
        # containing directory added to the front of the load path, and
        # cd into it, so both scripts and function files with names
        # that don't happen to match Octave's own path get found.
        script_dir = os.path.dirname(handle)
        stem = os.path.splitext(os.path.basename(handle))[0]

        executable = shutil.which(OCTAVE_EXECUTABLE)
        if executable is None:
            raise OctaveNotInstalledError(
                f"The Octave executable ({OCTAVE_EXECUTABLE!r}) was not "
                "found on PATH. Install GNU Octave on the grader host, or "
                "set the OCTAVE_EXECUTABLE environment variable to its "
                "absolute path."
            )

        eval_expr = self._build_eval_expression(options, stem)
        argv = [
            executable,
            "--no-gui",
            "--norc",
            "--no-init-file",
            "--quiet",
            "--eval",
            eval_expr,
        ]

        stdin_bytes = self._build_stdin(entries)
        env = self._safe_env()
        preexec = self._make_preexec_fn(options)

        try:
            proc = subprocess.Popen(  # noqa: S603 — argv is a fixed list, not shell
                argv,
                cwd=script_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                preexec_fn=preexec,
                start_new_session=True,
            )
        except FileNotFoundError as e:
            # Race: which() found the executable a moment ago but it
            # vanished before exec.  Convert to the same
            # not-installed error the up-front check produces.
            raise OctaveNotInstalledError(str(e)) from e

        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=stdin_bytes, timeout=options.time_limit
            )
        except subprocess.TimeoutExpired:
            # Kill the whole process group so any children spawned by
            # a runaway `.m` file die with it.  This mirrors what the
            # Python runtime's SIGALRM-based time_limit does.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:  # pragma: no cover — race
                pass
            # Drain what we have so the caller can still show partial
            # output in the log; ignore any decode errors here.
            try:
                stdout_bytes, _ = proc.communicate(timeout=1)
            except subprocess.TimeoutExpired:  # pragma: no cover
                stdout_bytes = b""
            self._tee_to_log(stdout_bytes, log)
            raise OctaveTimeoutError(
                f"Your `{options.obj_name}` took longer than "
                f"{options.time_limit} second(s) and was terminated."
            )

        self._tee_to_log(stdout_bytes, log)
        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
            raise OctaveRuntimeError(
                f"Octave exited with code {proc.returncode} while running "
                f"`{options.obj_name}`.",
                stderr=stderr_text,
            )

        return RuntimeResult(returned_values=None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_eval_expression(options: Options, stem: str) -> str:
        """Construct the ``--eval`` argument for the Octave subprocess.

        Two shapes:

        * **Script mode** (empty args and kwargs).  The eval expression
          is just the file's stem, which causes Octave to run the file
          top-to-bottom.  The stem is used verbatim so reference and
          student files with different stems (e.g. ``ref_main.m`` and
          ``main.m``) each execute their own contents.

        * **Function mode** (any args or kwargs supplied).  We call
          ``<obj_name>(<serialized args>)``.  The function must exist
          as either the top-of-file function of ``<stem>.m`` or as a
          subfunction inside it — Octave's usual name-resolution
          applies.

        We prefix both with an ``addpath`` for the script directory in
        case the caller's CWD differs from the file's directory (belt
        and braces — we also ``cd`` there via ``Popen(cwd=...)``).
        The ``try / catch`` wrapper turns any uncaught Octave error
        into a nonzero exit code with the message on stderr, which
        maps cleanly onto :class:`OctaveRuntimeError`.
        """
        # Script mode is signalled by an empty args/kwargs.  Because
        # the reference and student files typically have different
        # stems (e.g. ``ref_main.m`` vs ``main.m``), script mode runs
        # the file's actual stem, not ``obj_name`` — that way the
        # same ``Options.obj_name`` (used for error messages and
        # docstring generation) works for both sides.
        is_script = not options.args and not options.kwargs
        # ``stem`` and ``obj_name`` come from Options; they are the
        # student's filename / function name, so we deliberately do
        # not quote them (they must be valid Octave identifiers).
        if is_script:
            body = f"{stem};"
        else:
            body = f"{options.obj_name}{_format_args(options.args, options.kwargs)};"
        return dedent(
            f"""\
            try
              addpath(pwd);
              {body}
            catch err
              fprintf(stderr, '%s\\n', err.message);
              exit(1);
            end_try_catch
            exit(0);
            """
        )

    @staticmethod
    def _build_stdin(entries) -> bytes:
        """Encode ``entries`` as a newline-terminated stdin payload.

        ``entries`` may be an iterator (the caller passes
        ``self.entries``); we materialize it into a list here so the
        subprocess sees every entry even if the iterator has already
        been partially advanced.
        """
        materialized = list(entries)
        if not materialized:
            return b""
        return ("\n".join(str(e) for e in materialized) + "\n").encode("utf-8")

    @staticmethod
    def _safe_env() -> dict[str, str]:
        """Return a minimal, scrubbed environment for the Octave subprocess.

        We only forward variables Octave actually needs to start —
        ``PATH`` (to find its own shared libraries), ``HOME``
        (Octave writes a history file even in non-interactive mode),
        ``LANG`` / ``LC_ALL`` (locale), and ``OCTAVE_HISTFILE=/dev/null``
        so we don't accidentally leak state between the reference and
        student runs.  Everything else — including any grader-side
        ``PYTHONPATH``, tokens, or CI secrets — is dropped.
        """
        allow = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        env = {k: v for k, v in os.environ.items() if k in allow}
        # Belt and braces: even with --no-init-file / --norc, Octave
        # will still touch ~/.octave_hist unless we redirect it.
        env["OCTAVE_HISTFILE"] = "/dev/null"
        return env

    @staticmethod
    def _make_preexec_fn(options: Options):
        """Build a ``preexec_fn`` that applies POSIX resource limits.

        ``preexec_fn`` runs in the child between ``fork`` and ``exec``,
        so raising in it kills the child before Octave starts.  We
        clamp memory (``RLIMIT_AS``), CPU seconds (``RLIMIT_CPU``),
        maximum file size the child can create (``RLIMIT_FSIZE`` at 64
        MiB — plenty for a student output file, but small enough to
        stop accidental infinite loops from filling the disk), and the
        number of open file descriptors (``RLIMIT_NOFILE``).

        The CPU limit is set 1 second above ``time_limit`` so the
        wall-clock timeout (``communicate(timeout=...)``) can fire
        first and produce our nicer :class:`OctaveTimeoutError`
        message; the ``RLIMIT_CPU`` acts as a hard floor if the
        parent is somehow unable to kill the group.
        """
        mem_bytes = max(1, int(options.memory_limit_GB * _GB))
        cpu_seconds = max(1, int(options.time_limit) + 1)

        def preexec():  # pragma: no cover — runs post-fork
            # RLIMIT_AS: total virtual memory.  Same knob Python
            # runtime uses via `resource.setrlimit` in
            # `resource_limits.memory_limit`.
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

        # On non-POSIX platforms `resource` might be unavailable; the
        # runtime is POSIX-only by design (Gradescope + typical dev
        # boxes), and this refusal-to-boot is intentional so the
        # limits can't be silently skipped.
        if sys.platform == "win32":  # pragma: no cover — POSIX-only
            raise OctaveNotInstalledError(
                "The Octave runtime requires a POSIX host (Linux or macOS)."
            )
        return preexec

    @staticmethod
    def _tee_to_log(stdout_bytes: bytes, log) -> None:
        """Write captured stdout into ``log``.

        Decodes as UTF-8 with a replacement fallback (Octave's stdout
        may legitimately contain non-UTF-8 bytes if the student
        printed a raw uint8 array — we don't want that to crash the
        grader).  Respects the log's optional character limit — the
        same :class:`~generic_grader.utils.exceptions.LogLimitExceededError`
        that fires for Python code fires here too.
        """
        if not stdout_bytes:
            return
        text = stdout_bytes.decode("utf-8", errors="replace")
        log.write(text)


__all__ = (
    "OctaveNotInstalledError",
    "OctaveRuntime",
    "OctaveRuntimeError",
    "OctaveTimeoutError",
)
