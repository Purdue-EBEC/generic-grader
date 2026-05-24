"""Tests for the in-process security hardening layer.

This covers the new exceptions, patch factories, and `custom_stack`
integration introduced for issue #98 (defense-in-depth Layer 1).
"""

import builtins
import importlib
import os
from pathlib import Path

import pytest

from generic_grader.utils.exceptions import (
    DisallowedFileAccessError,
    DisallowedFunctionCallError,
    DisallowedImportError,
)
from generic_grader.utils.options import Options
from generic_grader.utils.patches import (
    BLOCKED_MODULES,
    custom_stack,
    make_dangerous_attr_patches,
    make_import_blocklist_patches,
    make_open_sandbox_patch,
)

# ---------------------------------------------------------------------------
# Exception messages
# ---------------------------------------------------------------------------


def test_disallowed_import_error_message():
    """DisallowedImportError should mention the module name."""
    err = DisallowedImportError("subprocess")
    assert "subprocess" in str(err)
    assert "not allowed" in str(err)


def test_disallowed_import_error_hint():
    """A custom hint should be appended after the default."""
    err = DisallowedImportError("socket", "Use the provided helpers instead.")
    assert "socket" in str(err)
    assert "Use the provided helpers instead." in str(err)


def test_disallowed_function_call_error_message():
    """DisallowedFunctionCallError should mention the function name."""
    err = DisallowedFunctionCallError("os.system")
    assert "os.system" in str(err)
    assert "not allowed" in str(err)


def test_disallowed_function_call_error_hint():
    """A custom hint should be appended after the default."""
    err = DisallowedFunctionCallError("subprocess.run", "Use input() instead.")
    assert "subprocess.run" in str(err)
    assert "Use input() instead." in str(err)


def test_disallowed_file_access_error_message():
    """DisallowedFileAccessError should mention the path."""
    err = DisallowedFileAccessError("/etc/passwd")
    assert "/etc/passwd" in str(err)
    assert "not allowed" in str(err)


def test_disallowed_file_access_error_hint():
    """A custom hint should be appended after the default."""
    err = DisallowedFileAccessError("results.json", "Use your own files.")
    assert "results.json" in str(err)
    assert "Use your own files." in str(err)


# ---------------------------------------------------------------------------
# Import blocklist patch factory
# ---------------------------------------------------------------------------


def test_blocked_modules_contains_high_risk():
    """The default blocklist should cover the dangerous module categories."""
    expected = {
        "subprocess",
        "socket",
        "ctypes",
        "multiprocessing",
        "urllib",
        "urllib.request",
        "http",
        "http.client",
        "requests",
        "ftplib",
        "smtplib",
        "telnetlib",
        "pty",
    }
    assert expected.issubset(BLOCKED_MODULES)


def test_make_import_blocklist_patches_targets():
    """Should patch both builtins.__import__ and importlib.import_module."""
    patches = make_import_blocklist_patches()
    targets = {p["args"][0] for p in patches}
    assert "builtins.__import__" in targets
    assert "importlib.import_module" in targets


def test_make_import_blocklist_patches_format():
    """Patches should load cleanly into Options."""
    result = make_import_blocklist_patches()
    assert Options(patches=result)


def test_import_blocklist_blocks_subprocess():
    """Importing subprocess inside custom_stack should raise."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            __import__("subprocess")


def test_import_blocklist_blocks_socket():
    """Importing socket inside custom_stack should raise."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            __import__("socket")


def test_import_blocklist_blocks_via_importlib():
    """importlib.import_module should also be blocked."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            importlib.import_module("subprocess")


def test_import_blocklist_blocks_submodule_of_blocked():
    """Submodules of a blocked top-level package should also be blocked."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            __import__("urllib.parse")


def test_import_blocklist_allows_safe_modules():
    """Common safe modules should still be importable."""
    o = Options()
    with custom_stack(o):
        # math is safe — should not raise.
        m = __import__("math")
        assert m.sqrt(4) == 2.0


def test_import_blocklist_allows_extra_blocked_param():
    """Callers may extend the blocklist via the extra_blocked parameter."""
    patches = make_import_blocklist_patches(extra_blocked=("json",))
    o = Options(patches=patches)
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            __import__("json")


def test_import_blocklist_allows_trusted_transitive_imports(tmp_path):
    """A trusted library that transitively imports a blocked module is allowed.

    Regression: numpy / matplotlib import `ctypes` internally; if we treat
    every import the same the moment student-driven test code triggers a
    fresh `numpy` load, the chain explodes. Imports whose immediate caller
    lives in a trusted directory (stdlib / site-packages / grader install)
    must bypass the blocklist.
    """
    from generic_grader.utils import patches as patches_mod

    # Forge a frame whose filename lives under one of the trusted dirs by
    # exec-ing source compiled with that filename. The `__import__` call
    # inside this exec runs with that synthetic filename as its caller.
    trusted_dir = patches_mod._TRUSTED_IMPORT_DIRS[0]
    fake_caller = os.path.join(trusted_dir, "fake_trusted_lib.py")
    src = "result = __import__('subprocess')\n"
    code = compile(src, fake_caller, "exec")

    o = Options()
    with custom_stack(o):
        ns = {}
        exec(code, ns)
        assert ns["result"] is not None


def test_import_blocklist_blocks_when_caller_is_student_code(tmp_path):
    """Same target, but the caller is an untrusted (student) location."""
    fake_caller = str(tmp_path / "student.py")
    src = "__import__('subprocess')\n"
    code = compile(src, fake_caller, "exec")

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            exec(code, {})


def test_import_blocklist_outside_stack_does_not_raise():
    """Outside custom_stack, imports should be unaffected."""
    # subprocess is heavy but importable. We do not actually need to use it.
    import subprocess  # noqa: F401

    assert subprocess is not None


# ---------------------------------------------------------------------------
# Dangerous attribute patches
# ---------------------------------------------------------------------------


def test_make_dangerous_attr_patches_format():
    """Patches should load cleanly into Options."""
    result = make_dangerous_attr_patches()
    assert Options(patches=result)


def test_make_dangerous_attr_patches_targets_include_os_system():
    """os.system should be in the dangerous-attr list."""
    targets = {p["args"][0] for p in make_dangerous_attr_patches()}
    assert "os.system" in targets


def test_make_dangerous_attr_patches_targets_include_signal_signal():
    """signal.signal should be patched so students cannot disable SIGALRM."""
    targets = {p["args"][0] for p in make_dangerous_attr_patches()}
    assert "signal.signal" in targets


def test_make_dangerous_attr_patches_targets_include_resource_setrlimit():
    """resource.setrlimit should be patched so students cannot raise limits."""
    targets = {p["args"][0] for p in make_dangerous_attr_patches()}
    assert "resource.setrlimit" in targets


def test_dangerous_attr_blocks_os_system():
    """Calling os.system inside custom_stack should raise."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFunctionCallError):
            os.system("echo hi")


def test_dangerous_attr_blocks_shutil_rmtree():
    """shutil.rmtree should be blocked."""
    import shutil

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFunctionCallError):
            shutil.rmtree("/tmp/does_not_matter")


def test_dangerous_attr_blocks_signal_signal():
    """Re-registering a signal handler should be blocked."""
    import signal

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFunctionCallError):
            signal.signal(signal.SIGALRM, lambda s, f: None)


def test_dangerous_attr_blocks_resource_setrlimit():
    """Raising a resource limit should be blocked."""
    import resource

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFunctionCallError):
            resource.setrlimit(resource.RLIMIT_AS, (resource.RLIM_INFINITY,) * 2)


# ---------------------------------------------------------------------------
# Sandboxed open()
# ---------------------------------------------------------------------------


def test_make_open_sandbox_patch_target():
    """The sandboxed open patch should target builtins.open."""
    patch = make_open_sandbox_patch()
    assert patch["args"][0] == "builtins.open"


def test_make_open_sandbox_patch_format():
    """Patch should load cleanly into Options."""
    patch = make_open_sandbox_patch()
    assert Options(patches=[patch])


def test_open_sandbox_blocks_reference_solution(tmp_path, monkeypatch):
    """Opening tests/reference.py should be blocked."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    ref = tmp_path / "tests" / "reference.py"
    ref.write_text("SECRET = 42\n")

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFileAccessError):
            open(ref)


def test_open_sandbox_blocks_results_json(tmp_path, monkeypatch):
    """Opening results.json should be blocked (regardless of mode)."""
    monkeypatch.chdir(tmp_path)
    rj = tmp_path / "results.json"
    rj.write_text("{}")

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFileAccessError):
            open(rj, "w")


def test_open_sandbox_blocks_grader_package(tmp_path, monkeypatch):
    """Opening anything inside the installed generic_grader package is blocked."""
    import generic_grader

    monkeypatch.chdir(tmp_path)
    pkg_init = Path(generic_grader.__file__)

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFileAccessError):
            open(pkg_init)


def test_open_sandbox_allows_student_files(tmp_path, monkeypatch):
    """Files in the submission directory should remain openable."""
    monkeypatch.chdir(tmp_path)
    student = tmp_path / "data.txt"
    student.write_text("hello")

    o = Options()
    with custom_stack(o):
        with open(student) as f:
            assert f.read() == "hello"


def test_open_sandbox_allows_extra_paths(tmp_path, monkeypatch):
    """Caller-supplied extra_allowed paths should bypass the block."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    expected = tmp_path / "tests" / "expected_output.txt"
    expected.write_text("data")

    patch = make_open_sandbox_patch(extra_allowed=(str(expected),))
    o = Options(patches=[patch])
    with custom_stack(o):
        with open(expected) as f:
            assert f.read() == "data"


def test_open_sandbox_blocks_tests_subdir(tmp_path, monkeypatch):
    """The whole tests/ subdirectory should be off-limits by default."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    config = tmp_path / "tests" / "config.py"
    config.write_text("# config")

    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedFileAccessError):
            open(config)


# ---------------------------------------------------------------------------
# custom_stack integration
# ---------------------------------------------------------------------------


def test_custom_stack_security_patches_on_by_default():
    """custom_stack should apply the security patches automatically."""
    o = Options()
    with custom_stack(o):
        # subprocess is in the default blocklist.
        with pytest.raises(DisallowedImportError):
            __import__("subprocess")


def test_custom_stack_security_disabled_flag():
    """When disable_security_patches=True, blocks should not fire."""
    o = Options(disable_security_patches=True)
    with custom_stack(o):
        # Import should succeed; we don't actually need to use it.
        sp = __import__("subprocess")
        assert sp is not None


# ---------------------------------------------------------------------------
# Edge cases for full coverage
# ---------------------------------------------------------------------------


def test_import_blocklist_blocks_relative_via_importlib():
    """Relative imports through importlib should resolve and be checked."""
    o = Options()
    with custom_stack(o):
        with pytest.raises(DisallowedImportError):
            # ".request" inside the (blocked) urllib package resolves to
            # urllib.request, which is blocked.
            importlib.import_module(".request", package="urllib")


def test_resolve_returns_none_for_non_path():
    """_resolve should swallow TypeError and return None for non-path args."""
    from generic_grader.utils.patches import _resolve

    assert _resolve(object()) is None


def test_open_sandbox_passes_through_file_descriptor(tmp_path, monkeypatch):
    """Passing an int file descriptor to open() should bypass path checks."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fd.txt"
    target.write_text("fd-data")
    fd = os.open(str(target), os.O_RDONLY)
    try:
        o = Options()
        with custom_stack(o):
            # closefd=False so the with-statement does not close our fd; we'll
            # close it ourselves in `finally`.
            with builtins.open(fd, closefd=False) as f:
                assert f.read() == "fd-data"
    finally:
        os.close(fd)


def test_open_sandbox_allows_extra_directory(tmp_path, monkeypatch):
    """extra_allowed should accept a directory, granting access to its files."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    target = tmp_path / "tests" / "expected_output.txt"
    target.write_text("value")

    patch_dict = make_open_sandbox_patch(extra_allowed=(str(tmp_path / "tests"),))
    o = Options(patches=[patch_dict])
    with custom_stack(o):
        with open(target) as f:
            assert f.read() == "value"


def test_open_sandbox_blocks_extra_blocked_path(tmp_path, monkeypatch):
    """extra_blocked should forbid a path the default rules would allow."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "secret.txt"
    target.write_text("shh")

    patch_dict = make_open_sandbox_patch(extra_blocked=(str(target),))
    o = Options(patches=[patch_dict])
    with custom_stack(o):
        with pytest.raises(DisallowedFileAccessError):
            open(target)


def test_is_inside_handles_value_error(tmp_path):
    """_is_inside (via sandboxed_open) should treat unrelated paths as outside.

    On POSIX, commonpath() between two absolute paths doesn't raise, but
    between a relative and absolute one it does. We exercise the catch-all
    by monkey-patching commonpath to raise ValueError unconditionally.
    """
    import generic_grader.utils.patches as patches_mod

    real_commonpath = os.path.commonpath

    def boom(*args, **kwargs):
        raise ValueError("forced")

    patch_dict = patches_mod.make_open_sandbox_patch(
        extra_allowed=(str(tmp_path),),
    )
    target = tmp_path / "x.txt"
    target.write_text("ok")

    # Replace commonpath so every _is_inside call hits ValueError. With
    # forced-False results, the file is not in the allowed set nor in any
    # protected directory, so the access should succeed via the final
    # real_open() call.
    os.path.commonpath = boom
    try:
        o = Options(patches=[patch_dict])
        with custom_stack(o):
            with open(target) as f:
                assert f.read() == "ok"
    finally:
        os.path.commonpath = real_commonpath


def test_caller_is_trusted_handles_top_of_stack(monkeypatch):
    """_caller_is_trusted should return False if it walks off the top of the
    stack without finding a non-skipped caller."""
    from generic_grader.utils import patches as patches_mod

    class FakeFrame:
        def __init__(self):
            self.f_code = type(
                "C",
                (),
                {"co_filename": "/usr/lib/python/importlib/_bootstrap.py"},
            )()

    def boom(depth):
        # Always return a skipped (importlib) frame, then run off the top
        # of the stack with ValueError.
        if depth > 5:
            raise ValueError("call stack is not deep enough")
        return FakeFrame()

    monkeypatch.setattr(patches_mod.sys, "_getframe", boom)
    assert patches_mod._caller_is_trusted() is False


def test_caller_is_trusted_handles_realpath_error(monkeypatch):
    """_caller_is_trusted should return False if realpath raises on the
    chosen frame's filename.
    """
    from generic_grader.utils import patches as patches_mod

    class FakeFrame:
        f_code = type("C", (), {"co_filename": "/some/student/file.py"})()

    monkeypatch.setattr(patches_mod.sys, "_getframe", lambda _: FakeFrame())
    monkeypatch.setattr(
        patches_mod.os.path,
        "realpath",
        lambda _: (_ for _ in ()).throw(OSError("forced")),
    )
    assert patches_mod._caller_is_trusted() is False


def test_security_wrapper_does_not_pollute_import_location_hint(tmp_path, monkeypatch):
    """`safe_import` should not appear in the student-facing import hint.

    Regression: the `safe_import` wrapper in `patches.py` sits on top of the
    real `__import__` on the traceback. Without filtering, the importer's
    location-hint search picks up the wrapper's `return real_import(...)`
    line (which contains the substring "import") instead of the student
    file that triggered the missing import.
    """
    from generic_grader.utils.importer import Importer

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "fake_module.py").write_text(
        "import fake_dependency\nfake_obj = lambda: None\n"
    )
    (tmp_path / "fake_dependency.py").write_text(
        "import fake_inner_module\nhelper = 1\n"
    )

    class FakeTest:
        failureException = AssertionError

        def fail(self, msg):
            raise self.failureException(msg)

    with pytest.raises(ModuleNotFoundError) as exc_info:
        Importer.import_obj(FakeTest(), "fake_module", Options(obj_name="fake_obj"))

    message = str(exc_info.value)
    assert "in `fake_dependency.py` on line 1:" in message
    assert "patches.py" not in message


def test_custom_stack_security_allows_user_patches_to_override():
    """A user-supplied patch on the same target should take precedence.

    `mock.patch` is LIFO — a later context-manager patch overrides earlier
    ones. The user patch is added after the security patches, so it wins.
    """
    from generic_grader.utils.mocks import make_mock_function_noop

    # User opts out of the import block on subprocess by re-patching to a no-op
    # importer that returns a sentinel module-like object.
    sentinel_module = object()

    def fake_import(name, *args, **kwargs):
        return sentinel_module

    o = Options(patches=[{"args": ("builtins.__import__", fake_import)}])
    with custom_stack(o):
        result = __import__("subprocess")
        assert result is sentinel_module

    # And the noop helper still works for unrelated targets.
    _ = make_mock_function_noop
