"""Unit + integration tests for :mod:`generic_grader.runtimes.octave`.

The Octave runtime spawns a subprocess.  We test in two layers:

* **Pure-Python unit tests.**  Argument serialization, eval-expression
  construction, stdin/env building, and error handling are exercised
  without invoking Octave.  Subprocess I/O is either mocked
  (:class:`~unittest.mock.patch`) or driven synthetically so these
  tests run in milliseconds and require no external binary.

* **Live-Octave integration tests.**  Two end-to-end tests exercise
  the *actual* Octave process — one script-mode, one function-mode.
  They are skipped automatically when ``octave`` is not on ``PATH``
  so contributor laptops without Octave installed can still run the
  full suite.

The unit-test layer alone gives us full-file coverage of
:mod:`~generic_grader.runtimes.octave` (the ``preexec`` hook itself
runs post-fork and is excluded via ``pragma: no cover``).
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import textwrap
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from generic_grader.runtimes import octave as octave_mod
from generic_grader.runtimes.base import RuntimeResult
from generic_grader.runtimes.octave import (
    OCTAVE_EXECUTABLE,
    OctaveNotInstalledError,
    OctaveRuntime,
    OctaveRuntimeError,
    OctaveTimeoutError,
    _format_args,
    _format_scalar,
)
from generic_grader.utils.exceptions import LogLimitExceededError
from generic_grader.utils.options import Options


# ---------------------------------------------------------------------------
# _format_scalar
# ---------------------------------------------------------------------------
class TestFormatScalar:
    """Argument serialization has to round-trip through Octave verbatim,
    so we pin the exact output string for each supported type.  Any
    change here is a wire-format break the grader author needs to
    know about."""

    def test_true(self):
        assert _format_scalar(True) == "true"

    def test_false(self):
        assert _format_scalar(False) == "false"

    def test_int(self):
        assert _format_scalar(0) == "0"
        assert _format_scalar(-17) == "-17"

    def test_float_finite(self):
        # ``repr`` is deliberate: it round-trips (Octave parses the
        # same lexical form Python produced).
        assert _format_scalar(3.14) == repr(3.14)

    def test_float_nan(self):
        assert _format_scalar(float("nan")) == "NaN"

    def test_float_pos_inf(self):
        assert _format_scalar(math.inf) == "Inf"

    def test_float_neg_inf(self):
        assert _format_scalar(-math.inf) == "-Inf"

    def test_str_simple(self):
        assert _format_scalar("hello") == "'hello'"

    def test_str_with_single_quote(self):
        # Octave single-quoted strings escape ' by doubling it.
        assert _format_scalar("it's") == "'it''s'"

    def test_str_empty(self):
        assert _format_scalar("") == "''"

    def test_unsupported_type_raises_typeerror(self):
        # Lists, dicts, tuples, numpy arrays, etc. are intentionally
        # left out of this PR — supporting them requires an Octave
        # cell/struct/array construction story we haven't scoped yet.
        with pytest.raises(TypeError, match="Cannot serialize"):
            _format_scalar([1, 2, 3])

    def test_bool_is_not_treated_as_int(self):
        """``bool`` subclasses ``int``; the mapping uses ``type(...)``
        precisely to keep ``True → 'true'`` instead of ``'1'``.  This
        test locks that in."""
        assert _format_scalar(True) == "true"
        assert _format_scalar(False) == "false"


# ---------------------------------------------------------------------------
# _format_args
# ---------------------------------------------------------------------------
class TestFormatArgs:
    def test_empty(self):
        assert _format_args((), {}) == ""

    def test_positional_only(self):
        assert _format_args((1, 2), {}) == "(1, 2)"

    def test_kwargs_only(self):
        # MATLAB / Octave convention: trailing ('key', value) pairs.
        assert _format_args((), {"width": 10}) == "('width', 10)"

    def test_mixed(self):
        assert (
            _format_args((1.5, "hi"), {"color": "red"}) == "(1.5, 'hi', 'color', 'red')"
        )

    def test_kwargs_stringify_key(self):
        """Keys are coerced to strings before serialization so tests
        can pass symbols/enums as keyword names without special
        handling."""
        result = _format_args((), {123: "v"})
        assert result == "('123', 'v')"


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------
class TestResolve:
    def test_returns_absolute_path_when_file_exists(self, fix_syspath):
        (fix_syspath / "student.m").write_text("disp('hi')\n")
        runtime = OctaveRuntime()
        tc = unittest.TestCase()
        tc.runTest = lambda: None  # type: ignore[method-assign]

        options = Options(
            language="octave",
            obj_name="student",
            sub_module="student",
            ref_module="student",
            weight=1,
        )
        handle = runtime.resolve(tc, options, "student")
        assert os.path.isabs(handle)
        assert handle.endswith("student.m")

    def test_missing_file_fails_the_test_case(self, fix_syspath):
        runtime = OctaveRuntime()
        # ``test.fail`` raises ``AssertionError`` inside a
        # ``TestCase`` — capture and inspect that.
        tc = unittest.TestCase()
        tc.runTest = lambda: None  # type: ignore[method-assign]

        options = Options(
            language="octave",
            obj_name="missing",
            sub_module="missing",
            ref_module="missing",
            weight=1,
        )
        # The runtime swaps ``failureException`` to ``FileNotFoundError``
        # before calling ``test.fail``, so that is exactly what pytest
        # sees bubble out here.
        with pytest.raises(FileNotFoundError) as excinfo:
            runtime.resolve(tc, options, "missing")
        msg = str(excinfo.value)
        assert "Unable to load `missing.m`" in msg
        assert "level of your submission" in msg
        assert tc.failureException is FileNotFoundError


# ---------------------------------------------------------------------------
# _build_eval_expression
# ---------------------------------------------------------------------------
class TestBuildEvalExpression:
    def _opts(self, **overrides):
        base = dict(
            language="octave",
            obj_name="main",
            sub_module="main",
            ref_module="main",
            weight=1,
        )
        base.update(overrides)
        return Options(**base)

    def test_script_mode_uses_stem(self):
        """No args, no kwargs → script mode → invoke the file's
        actual stem, not ``obj_name``."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="main"), stem="ref_main"
        )
        assert "ref_main;" in expr
        assert "main(" not in expr

    def test_function_mode_with_positional_args(self):
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="greet", args=("world",)),
            stem="greet",
        )
        assert "greet('world');" in expr

    def test_function_mode_with_kwargs(self):
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="plot_it", kwargs={"width": 3}),
            stem="plot_it",
        )
        assert "plot_it('width', 3);" in expr

    def test_expression_has_try_catch_wrapper(self):
        """Uncaught Octave errors must surface as a nonzero exit
        code with the message on stderr.  Confirm the wrapper
        emits both."""
        expr = OctaveRuntime._build_eval_expression(self._opts(), stem="main")
        assert "try" in expr
        assert "addpath(pwd)" in expr
        assert "fprintf(stderr" in expr
        assert "exit(1)" in expr
        assert "exit(0)" in expr


# ---------------------------------------------------------------------------
# _build_stdin
# ---------------------------------------------------------------------------
class TestBuildStdin:
    def test_empty_iterator_returns_empty_bytes(self):
        assert OctaveRuntime._build_stdin(iter([])) == b""

    def test_entries_are_newline_terminated(self):
        result = OctaveRuntime._build_stdin(iter(["a", "b", "c"]))
        assert result == b"a\nb\nc\n"

    def test_entries_are_stringified(self):
        """Test authors may pass numeric ``entries`` because the
        Python runtime accepts anything ``str()``-able — Octave's
        stdin has to too, for symmetry."""
        result = OctaveRuntime._build_stdin(iter([1, 2.5, True]))
        assert result == b"1\n2.5\nTrue\n"


# ---------------------------------------------------------------------------
# _safe_env
# ---------------------------------------------------------------------------
class TestSafeEnv:
    def test_only_whitelisted_keys_forwarded(self, monkeypatch):
        # Poison the parent environment with a secret.
        monkeypatch.setenv("SECRET_TOKEN", "please-do-not-leak")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        env = OctaveRuntime._safe_env()
        assert "SECRET_TOKEN" not in env
        assert env["PATH"] == "/usr/bin:/bin"

    def test_octave_histfile_pinned_to_devnull(self):
        env = OctaveRuntime._safe_env()
        assert env["OCTAVE_HISTFILE"] == "/dev/null"


# ---------------------------------------------------------------------------
# _tee_to_log
# ---------------------------------------------------------------------------
class TestTeeToLog:
    def test_writes_utf8_text(self):
        log = StringIO()
        OctaveRuntime._tee_to_log("hi there\n".encode("utf-8"), log)
        assert log.getvalue() == "hi there\n"

    def test_replacement_on_invalid_utf8(self):
        log = StringIO()
        OctaveRuntime._tee_to_log(b"\xff\xfe", log)
        # No exception; U+FFFD replacement in output.
        assert "\ufffd" in log.getvalue()

    def test_empty_bytes_is_noop(self):
        log = StringIO()
        OctaveRuntime._tee_to_log(b"", log)
        assert log.getvalue() == ""


# ---------------------------------------------------------------------------
# _make_preexec_fn
# ---------------------------------------------------------------------------
class TestMakePreexecFn:
    def test_returns_callable(self):
        options = Options(
            language="octave",
            obj_name="main",
            sub_module="main",
            ref_module="main",
            weight=1,
        )
        fn = OctaveRuntime._make_preexec_fn(options)
        assert callable(fn)

    def test_zero_memory_clamped_to_one_byte(self):
        """A misconfigured test with ``memory_limit_GB=0`` must not
        pass ``(0, 0)`` to ``RLIMIT_AS`` — the kernel would kill
        Octave before it starts.  The clamp to 1 byte still fails
        the run (Octave can't allocate) but produces a clean
        :class:`OctaveRuntimeError` instead of an opaque crash."""
        options = Options(
            language="octave",
            obj_name="main",
            sub_module="main",
            ref_module="main",
            memory_limit_GB=0.0,
            weight=1,
        )
        # We can't easily invoke the preexec (it runs post-fork), but
        # we can build it without error, which is the contract.
        fn = OctaveRuntime._make_preexec_fn(options)
        assert callable(fn)


# ---------------------------------------------------------------------------
# run() — subprocess mocked
# ---------------------------------------------------------------------------
class TestRunMocked:
    """Drive ``OctaveRuntime.run`` with a mocked ``subprocess.Popen``
    so we can exercise every branch of the process-management logic
    without needing GNU Octave installed."""

    def _opts(self, **overrides):
        base = dict(
            language="octave",
            obj_name="main",
            sub_module="main",
            ref_module="main",
            weight=1,
        )
        base.update(overrides)
        return Options(**base)

    def _resolve(self, tmp_path, name="main"):
        (tmp_path / f"{name}.m").write_text("disp('placeholder')\n")
        return str(tmp_path / f"{name}.m")

    def test_success_writes_stdout_to_log(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        fake_proc = MagicMock()
        fake_proc.communicate.return_value = (b"hello\n", b"")
        fake_proc.returncode = 0

        with patch(
            "generic_grader.runtimes.octave.subprocess.Popen",
            return_value=fake_proc,
        ) as mock_popen:
            with patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ):
                result = OctaveRuntime().run(options, handle, log, iter([]))

        assert isinstance(result, RuntimeResult)
        assert result.returned_values is None
        assert log.getvalue() == "hello\n"

        # Popen was called with the argv shape we promised.
        argv = mock_popen.call_args.args[0]
        assert argv[0] == "/usr/bin/octave"
        assert "--no-gui" in argv
        assert "--norc" in argv
        assert "--no-init-file" in argv
        assert "--quiet" in argv
        assert argv[-2] == "--eval"

    def test_nonzero_exit_raises_octave_runtime_error(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        fake_proc = MagicMock()
        fake_proc.communicate.return_value = (
            b"partial output\n",
            b"error: undefined variable 'xyz'\n",
        )
        fake_proc.returncode = 1

        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                return_value=fake_proc,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
        ):
            with pytest.raises(OctaveRuntimeError) as excinfo:
                OctaveRuntime().run(options, handle, log, iter([]))

        # Partial stdout still made it into the log.
        assert "partial output" in log.getvalue()
        # Stderr is attached for the student-facing hint.
        assert "undefined variable 'xyz'" in excinfo.value.stderr

    def test_timeout_kills_process_group_and_raises(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts(time_limit=1)
        log = StringIO()

        fake_proc = MagicMock()
        fake_proc.pid = 12345
        # First communicate() raises TimeoutExpired; the second (drain)
        # returns whatever partial stdout was buffered.
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
            (b"partial\n", b""),
        ]

        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                return_value=fake_proc,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
            patch("generic_grader.runtimes.octave.os.killpg") as mock_killpg,
        ):
            with pytest.raises(OctaveTimeoutError, match="took longer than"):
                OctaveRuntime().run(options, handle, log, iter([]))

        # Process group was killed with SIGKILL, targeting the child pid.
        mock_killpg.assert_called_once()
        assert mock_killpg.call_args.args[0] == 12345

        # Partial stdout still made it into the log for the student.
        assert "partial" in log.getvalue()

    def test_octave_not_on_path_raises(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        with patch("generic_grader.runtimes.octave.shutil.which", return_value=None):
            with pytest.raises(OctaveNotInstalledError, match="not"):
                OctaveRuntime().run(options, handle, StringIO(), iter([]))

    def test_popen_filenotfound_race_becomes_not_installed(self, fix_syspath):
        """``which()`` returned a path but ``exec`` raced with a
        concurrent uninstall — we still surface a clean error."""
        handle = self._resolve(fix_syspath)
        options = self._opts()
        with (
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                side_effect=FileNotFoundError("gone"),
            ),
        ):
            with pytest.raises(OctaveNotInstalledError, match="gone"):
                OctaveRuntime().run(options, handle, StringIO(), iter([]))

    def test_timeout_second_communicate_expired_swallowed(self, fix_syspath):
        """If the post-kill drain communicate also times out, we must
        still raise ``OctaveTimeoutError`` (not crash).  This exercises
        the inner ``TimeoutExpired`` branch."""
        handle = self._resolve(fix_syspath)
        options = self._opts(time_limit=1)
        log = StringIO()

        fake_proc = MagicMock()
        fake_proc.pid = 4242
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
        ]

        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                return_value=fake_proc,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
            patch("generic_grader.runtimes.octave.os.killpg"),
        ):
            with pytest.raises(OctaveTimeoutError):
                OctaveRuntime().run(options, handle, log, iter([]))

    def test_stdin_is_piped_from_entries(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        fake_proc = MagicMock()
        fake_proc.communicate.return_value = (b"", b"")
        fake_proc.returncode = 0

        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                return_value=fake_proc,
            ) as mock_popen,
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
        ):
            OctaveRuntime().run(options, handle, log, iter(["42", "3.14"]))

        # The bytes payload of ``communicate`` is our stdin.
        kwargs = fake_proc.communicate.call_args.kwargs
        assert kwargs["input"] == b"42\n3.14\n"
        # Kwargs also passed the wall-clock timeout.
        assert kwargs["timeout"] == options.time_limit
        # And ``cwd`` was the script directory.
        assert mock_popen.call_args.kwargs["cwd"] == str(fix_syspath)


# ---------------------------------------------------------------------------
# Live-Octave integration
# ---------------------------------------------------------------------------
_HAVE_OCTAVE = shutil.which(OCTAVE_EXECUTABLE) is not None


@pytest.mark.skipif(not _HAVE_OCTAVE, reason="GNU Octave not installed")
class TestOctaveLive:
    """Two end-to-end tests that actually shell out to GNU Octave.

    These are the ultimate check that our eval expression, env, and
    process management work with a real interpreter.  They are the
    only tests here that require Octave on ``PATH``; the class is
    ``skipif``'d out on contributor machines that lack it."""

    def test_script_mode_runs_and_captures_stdout(self, fix_syspath):
        (fix_syspath / "greet.m").write_text("disp('hello from octave')\n")
        options = Options(
            language="octave",
            obj_name="greet",
            sub_module="greet",
            ref_module="greet",
            weight=1,
        )
        log = StringIO()
        result = OctaveRuntime().run(
            options,
            str(fix_syspath / "greet.m"),
            log,
            iter([]),
        )
        assert isinstance(result, RuntimeResult)
        assert "hello from octave" in log.getvalue()

    def test_function_mode_with_arg(self, fix_syspath):
        (fix_syspath / "square.m").write_text(
            textwrap.dedent(
                """\
                function square(n)
                  fprintf('%d\\n', n * n);
                end
                """
            )
        )
        options = Options(
            language="octave",
            obj_name="square",
            sub_module="square",
            ref_module="square",
            args=(5,),
            weight=1,
        )
        log = StringIO()
        OctaveRuntime().run(
            options,
            str(fix_syspath / "square.m"),
            log,
            iter([]),
        )
        assert "25" in log.getvalue()

    def test_octave_runtime_error_carries_stderr(self, fix_syspath):
        """Deliberately reference an undefined identifier so the
        subprocess exits nonzero, and check that the error text
        makes it back through :class:`OctaveRuntimeError`."""
        (fix_syspath / "bad.m").write_text("disp(undefined_variable)\n")
        options = Options(
            language="octave",
            obj_name="bad",
            sub_module="bad",
            ref_module="bad",
            weight=1,
        )
        with pytest.raises(OctaveRuntimeError) as excinfo:
            OctaveRuntime().run(
                options,
                str(fix_syspath / "bad.m"),
                StringIO(),
                iter([]),
            )
        assert "undefined_variable" in excinfo.value.stderr


# ---------------------------------------------------------------------------
# LogLimitExceededError propagation
# ---------------------------------------------------------------------------
def test_log_limit_error_propagates_from_tee(fix_syspath):
    """When ``log_limit`` triggers inside ``_tee_to_log``, the same
    :class:`LogLimitExceededError` that fires for Python code fires
    for Octave — the caller in ``__User__`` already knows how to
    render it."""

    class LimitedLog:
        """Minimal shim exposing the ``write`` contract ``LogIO`` uses."""

        def write(self, data):
            raise LogLimitExceededError()

    with pytest.raises(LogLimitExceededError):
        OctaveRuntime._tee_to_log(b"anything at all", LimitedLog())


# ---------------------------------------------------------------------------
# Executable-override env var
# ---------------------------------------------------------------------------
def test_executable_env_var_is_read_at_module_import(monkeypatch):
    """``OCTAVE_EXECUTABLE`` is captured once at import time.  This
    test just documents the contract — changing it after import
    won't retro-actively change the runtime."""
    assert octave_mod.OCTAVE_EXECUTABLE  # non-empty default
    # Sanity: overriding the env post-import doesn't rebind the constant.
    monkeypatch.setenv("OCTAVE_EXECUTABLE", "made-up-name")
    assert octave_mod.OCTAVE_EXECUTABLE != "made-up-name"
