"""Tests for grader-internal fault attribution.

A security exception raised from *library* code (e.g. matplotlib's
font-cache cleanup) is a grader bug, not a student error.  These tests pin
down the classifier that distinguishes the two.  See issue #198.
"""

import logging
import os

import pytest

from generic_grader.utils import attribution as attribution_mod
from generic_grader.utils import exceptions
from generic_grader.utils.attribution import is_grader_internal_fault
from generic_grader.utils.exceptions import DisallowedFunctionCallError
from generic_grader.utils.options import Options
from generic_grader.utils.patches import custom_stack


def _run_as(filename, src):
    """Execute `src` with every frame attributed to `filename`.

    This forges the caller location the classifier inspects, so a test can
    pretend to be an installed library or a student submission.
    """
    exec(compile(src, filename, "exec"), {})


def _library_file():
    return os.path.join(attribution_mod._LIBRARY_DIRS[0], "fake_lib", "core.py")


def _student_file(tmp_path):
    return str(tmp_path / "student.py")


# ---------------------------------------------------------------------------
# Direct calls
# ---------------------------------------------------------------------------


def test_library_direct_unlink_is_internal_fault(tmp_path):
    """A blocked call made directly by library code is a grader fault."""
    target = tmp_path / "lockfile"
    target.write_text("")

    with custom_stack(Options()):
        with pytest.raises(DisallowedFunctionCallError) as info:
            _run_as(_library_file(), f"import os\nos.unlink({str(target)!r})\n")

    assert is_grader_internal_fault(info.value) is True


def test_student_direct_unlink_is_not_internal_fault(tmp_path):
    """A blocked call made directly by student code is a student error."""
    target = tmp_path / "victim"
    target.write_text("")

    with custom_stack(Options()):
        with pytest.raises(DisallowedFunctionCallError) as info:
            _run_as(_student_file(tmp_path), f"import os\nos.unlink({str(target)!r})\n")

    assert is_grader_internal_fault(info.value) is False


# ---------------------------------------------------------------------------
# Calls laundered through a stdlib wrapper (pathlib)
# ---------------------------------------------------------------------------


def test_library_pathlib_unlink_is_internal_fault(tmp_path):
    """Library -> pathlib (stdlib) -> blocked call is still a grader fault.

    This is the exact chain matplotlib uses when writing its font cache:
    cbook._lock_path -> Path.unlink -> os.unlink.
    """
    target = tmp_path / "lockfile"
    target.write_text("")

    with custom_stack(Options()):
        with pytest.raises(DisallowedFunctionCallError) as info:
            _run_as(
                _library_file(),
                f"import pathlib\npathlib.Path({str(target)!r}).unlink()\n",
            )

    assert is_grader_internal_fault(info.value) is True


def test_student_pathlib_unlink_is_not_internal_fault(tmp_path):
    """Student -> pathlib (stdlib) -> blocked call is a student error.

    pathlib lives in the stdlib, so trusting the immediate caller would
    misattribute this as a grader fault.
    """
    target = tmp_path / "victim"
    target.write_text("")

    with custom_stack(Options()):
        with pytest.raises(DisallowedFunctionCallError) as info:
            _run_as(
                _student_file(tmp_path),
                f"import pathlib\npathlib.Path({str(target)!r}).unlink()\n",
            )

    assert is_grader_internal_fault(info.value) is False


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_library_non_grader_error_is_not_internal_fault():
    """A library's own exception is not a grader fault.

    Only the grader's security errors can be grader faults; otherwise a
    library `ValueError` caused by student misuse would be misreported.
    """
    with pytest.raises(ValueError) as info:
        _run_as(_library_file(), "raise ValueError('boom')\n")

    assert is_grader_internal_fault(info.value) is False


def test_no_traceback_is_not_internal_fault():
    """An exception that was never raised has no origin to classify."""
    assert is_grader_internal_fault(DisallowedFunctionCallError("os.unlink")) is False


def test_grader_machinery_only_is_not_internal_fault():
    """An exception raised purely from grader machinery is not a library fault."""
    with pytest.raises(DisallowedFunctionCallError) as info:
        raise DisallowedFunctionCallError("os.unlink")

    assert is_grader_internal_fault(info.value) is False


def test_dynamically_compiled_frame_is_skipped():
    """Frames from dynamically compiled code are transparent."""
    with pytest.raises(DisallowedFunctionCallError) as info:
        _run_as(
            "<string>",
            "from generic_grader.utils.exceptions import DisallowedFunctionCallError\n"
            "raise DisallowedFunctionCallError('os.unlink')\n",
        )

    assert is_grader_internal_fault(info.value) is False


def test_frozen_frame_between_library_and_block_is_transparent():
    """`<frozen os>` frames (Python 3.11+) must not hide a library origin."""
    frozen_ns = {}
    exec(
        compile(
            "from generic_grader.utils.exceptions import DisallowedFunctionCallError\n"
            "def blocked():\n"
            "    raise DisallowedFunctionCallError('os.unlink')\n",
            "<frozen os>",
            "exec",
        ),
        frozen_ns,
    )
    lib_ns = {}
    exec(compile("def run(f):\n    f()\n", _library_file(), "exec"), lib_ns)

    with pytest.raises(DisallowedFunctionCallError) as info:
        lib_ns["run"](frozen_ns["blocked"])

    assert is_grader_internal_fault(info.value) is True


def test_is_pseudo_file_matches_only_angle_bracket_names():
    assert attribution_mod._is_pseudo_file("<string>") is True
    assert attribution_mod._is_pseudo_file("<frozen importlib._bootstrap>") is True
    assert attribution_mod._is_pseudo_file("/tmp/<odd>/file.py") is False
    assert attribution_mod._is_pseudo_file("student.py") is False


def test_library_package_named_importlib_is_still_a_library():
    """Skipping must not be a substring match on path components."""
    path = os.path.join(attribution_mod._LIBRARY_DIRS[0], "importlib", "core.py")

    with custom_stack(Options()):
        with pytest.raises(DisallowedFunctionCallError) as info:
            _run_as(path, "import os\nos.unlink('x')\n")

    assert is_grader_internal_fault(info.value) is True


def test_grader_dir_is_the_package_directory():
    """`_GRADER_DIR` is the package dir, not its parent (site-packages)."""
    import generic_grader

    expected = os.path.realpath(os.path.dirname(generic_grader.__file__))
    assert attribution_mod._GRADER_DIR == expected
    assert os.path.basename(attribution_mod._GRADER_DIR) == "generic_grader"


def test_installed_grader_frames_are_transparent_but_sibling_libraries_are_not(
    tmp_path, monkeypatch
):
    """With the grader installed in site-packages, only its own package is skipped."""
    libdir = (tmp_path / "site-packages").resolve()
    monkeypatch.setattr(attribution_mod, "_LIBRARY_DIRS", (str(libdir),))
    monkeypatch.setattr(attribution_mod, "_GRADER_DIR", str(libdir / "generic_grader"))
    src = (
        "from generic_grader.utils.exceptions import DisallowedFunctionCallError\n"
        "raise DisallowedFunctionCallError('os.unlink')\n"
    )

    with pytest.raises(DisallowedFunctionCallError) as sibling:
        _run_as(str(libdir / "other_lib" / "core.py"), src)
    assert is_grader_internal_fault(sibling.value) is True

    with pytest.raises(DisallowedFunctionCallError) as own:
        _run_as(str(libdir / "generic_grader" / "patches.py"), src)
    assert is_grader_internal_fault(own.value) is False


SECURITY_ERRORS = (
    ("DisallowedImportError", "'socket'"),
    ("DisallowedFunctionCallError", "'os.unlink'"),
    ("DisallowedFileAccessError", "'secret.txt'"),
)

LIMIT_ERRORS = (
    ("UserTimeoutError", ""),
    ("ExitError", ""),
    ("QuitError", ""),
    ("LogLimitExceededError", ""),
    ("EndOfInputError", ""),
    ("ExcessFunctionCallError", "'helper'"),
)


def _raise_src(name, args):
    return (
        "from generic_grader.utils import exceptions\n"
        f"raise exceptions.{name}({args})\n"
    )


def test_every_security_error_from_library_is_internal_fault():
    for name, args in SECURITY_ERRORS:
        with pytest.raises(getattr(exceptions, name)) as info:
            _run_as(_library_file(), _raise_src(name, args))
        assert is_grader_internal_fault(info.value) is True, name


def test_limit_errors_from_library_are_not_internal_faults():
    """Timeouts, exit, input and log limits are student outcomes, even in a library."""
    for name, args in LIMIT_ERRORS:
        with pytest.raises(getattr(exceptions, name)) as info:
            _run_as(_library_file(), _raise_src(name, args))
        assert is_grader_internal_fault(info.value) is False, name


def test_is_inside_handles_incomparable_paths():
    """`_is_inside` returns False when paths cannot be compared."""
    assert attribution_mod._is_inside("/absolute/path", "relative/path") is False


def test_unresolvable_frame_path_is_not_internal_fault(monkeypatch):
    """A frame whose path cannot be resolved is not treated as a library fault."""
    with pytest.raises(DisallowedFunctionCallError) as info:
        _run_as(
            _library_file(),
            "from generic_grader.utils.exceptions import DisallowedFunctionCallError\n"
            "raise DisallowedFunctionCallError('os.unlink')\n",
        )
    assert is_grader_internal_fault(info.value) is True

    monkeypatch.setattr(
        attribution_mod.os.path,
        "realpath",
        lambda _: (_ for _ in ()).throw(OSError("forced")),
    )
    assert is_grader_internal_fault(info.value) is False


# ---------------------------------------------------------------------------
# Library-dir discovery
# ---------------------------------------------------------------------------


def test_library_dirs_include_site_package_locations(tmp_path, monkeypatch):
    dist = str((tmp_path / "dist-packages").resolve())
    user = str((tmp_path / "user-site").resolve())
    monkeypatch.setattr(attribution_mod.site, "getsitepackages", lambda: [dist])
    monkeypatch.setattr(attribution_mod.site, "getusersitepackages", lambda: user)

    dirs = attribution_mod._compute_library_dirs()

    assert dist in dirs
    assert user in dirs


def test_library_dirs_tolerate_missing_user_site_and_getsitepackages(monkeypatch):
    monkeypatch.setattr(attribution_mod.site, "getusersitepackages", lambda: None)
    monkeypatch.delattr(attribution_mod.site, "getsitepackages")

    dirs = attribution_mod._compute_library_dirs()

    assert dirs
    assert all(isinstance(d, str) for d in dirs)


def test_library_nested_inside_stdlib_is_library_not_stdlib(tmp_path, monkeypatch):
    """Library dirs win over stdlib dirs regardless of the host layout."""
    stdlib = (tmp_path / "lib" / "python3").resolve()
    monkeypatch.setattr(attribution_mod, "_STDLIB_DIRS", (str(stdlib),))
    monkeypatch.setattr(
        attribution_mod, "_LIBRARY_DIRS", (str(stdlib / "site-packages"),)
    )
    src = (
        "from generic_grader.utils.exceptions import DisallowedFunctionCallError\n"
        "raise DisallowedFunctionCallError('os.unlink')\n"
    )

    with pytest.raises(DisallowedFunctionCallError) as lib:
        _run_as(str(stdlib / "site-packages" / "lib" / "core.py"), src)
    assert is_grader_internal_fault(lib.value) is True

    # A stdlib frame is transparent, so the student frame in this test decides.
    with pytest.raises(DisallowedFunctionCallError) as std:
        _run_as(str(stdlib / "json" / "decoder.py"), src)
    assert is_grader_internal_fault(std.value) is False


# ---------------------------------------------------------------------------
# Grader-fault detail
# ---------------------------------------------------------------------------


def test_report_grader_fault_names_type_and_library_basename():
    with pytest.raises(DisallowedFunctionCallError) as info:
        _run_as(
            _library_file(), _raise_src("DisallowedFunctionCallError", "'os.unlink'")
        )

    detail = attribution_mod.report_grader_fault(info.value)

    assert detail == "`DisallowedFunctionCallError` raised in `core.py`"
    assert "fake_lib" not in detail


def test_report_grader_fault_sanitizes_untrusted_basename():
    filename = os.path.join(os.path.dirname(_library_file()), "ev`il\nname.py")
    with pytest.raises(DisallowedFunctionCallError) as info:
        _run_as(filename, _raise_src("DisallowedFunctionCallError", "'os.unlink'"))

    detail = attribution_mod.report_grader_fault(info.value)

    assert detail == "`DisallowedFunctionCallError` raised in `ev_il_name.py`"


def test_report_grader_fault_returns_none_and_logs_nothing_for_student_error(caplog):
    with caplog.at_level("ERROR"):
        detail = attribution_mod.report_grader_fault(DisallowedFunctionCallError("x"))

    assert detail is None
    assert caplog.records == []


# ---------------------------------------------------------------------------
# Instructor-facing log
# ---------------------------------------------------------------------------


def test_report_grader_fault_logs_traceback_origin_and_message(caplog):
    with pytest.raises(DisallowedFunctionCallError) as info:
        _run_as(
            _library_file(), _raise_src("DisallowedFunctionCallError", "'os.unlink'")
        )

    with caplog.at_level("ERROR", logger="generic_grader.utils.attribution"):
        attribution_mod.report_grader_fault(info.value)

    (record,) = caplog.records
    assert record.exc_info[1] is info.value
    text = record.getMessage()
    assert _library_file() in text
    assert "os.unlink" in text
    assert "student" in text  # flags the possible student-triggered case


def test_logger_has_null_handler_so_stderr_stays_student_safe():
    """Without a handler, the last-resort handler prints the traceback to stderr."""
    handlers = attribution_mod._logger.handlers

    assert any(isinstance(h, logging.NullHandler) for h in handlers)


# ---------------------------------------------------------------------------
# Known limitations (documented, not mitigated)
# ---------------------------------------------------------------------------


def test_known_limitation_student_callback_through_library_is_attributed_to_grader(
    tmp_path,
):
    """Documents a limitation: a blocked callable handed to library code.

    The traceback cannot tell this apart from a library calling the blocked
    function itself.  Only the message is affected; the call is still blocked.
    See the module docstring before reusing this classifier as an allow-list.
    """
    target = tmp_path / "victim"
    target.write_text("")
    lib_ns = {}
    exec(compile("def apply(f, p):\n    f(p)\n", _library_file(), "exec"), lib_ns)

    with custom_stack(Options()):
        import os as patched_os

        with pytest.raises(DisallowedFunctionCallError) as info:
            lib_ns["apply"](patched_os.unlink, str(target))

    assert target.exists()
    assert is_grader_internal_fault(info.value) is True


def test_known_limitation_filename_is_not_authenticated(tmp_path):
    """Documents a limitation: student code can compile under a library filename."""
    target = tmp_path / "victim"
    target.write_text("")
    src = f"import os\nos.unlink({str(target)!r})\n"

    with custom_stack(Options()):
        with pytest.raises(DisallowedFunctionCallError) as as_student:
            _run_as(_student_file(tmp_path), src)
        with pytest.raises(DisallowedFunctionCallError) as as_library:
            _run_as(_library_file(), src)

    assert target.exists()
    assert is_grader_internal_fault(as_student.value) is False
    assert is_grader_internal_fault(as_library.value) is True
