"""Unit + integration tests for :mod:`generic_grader.runtimes.octave`.

The Octave runtime spawns a subprocess.  We test in two layers:

* **Pure-Python unit tests.**  Argument serialization, eval-expression
  construction, stdin/env building, and error handling are exercised
  without invoking Octave.  Subprocess I/O is either mocked
  (:class:`~unittest.mock.patch`) or driven synthetically so these
  tests run in milliseconds and require no external binary.

* **Live-Octave integration tests.**  End-to-end tests exercise the
  *actual* Octave process — script mode, function mode, resource
  limits, output overflow, stdin entries, and process-group reaping.
  They are skipped automatically when ``octave`` is not on ``PATH``
  so contributor laptops without Octave installed can still run the
  full suite.

The unit-test layer alone gives us full-file coverage of
:mod:`~generic_grader.runtimes.octave`; the rlimit launcher is
additionally exercised for real in a live subprocess test.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import textwrap
import time
import unittest
from contextlib import ExitStack
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch

import pytest

from generic_grader.runtimes import octave as octave_mod
from generic_grader.runtimes.base import RuntimeResult
from generic_grader.runtimes.octave import (
    _LAUNCHER,
    FILE_SIZE_LIMIT,
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

    def test_invalid_module_name_is_rejected(self, fix_syspath):
        """Non-identifier stems are grader misconfiguration: ValueError,
        not a student-facing ``test.fail``."""
        tc = unittest.TestCase()
        tc.runTest = lambda: None  # type: ignore[method-assign]
        options = Options(language="octave", weight=1)

        for bad in ("foo; system('x')", "my main", "1main", "tests.reference"):
            with pytest.raises(ValueError, match="valid identifier"):
                OctaveRuntime().resolve(tc, options, bad)


# ---------------------------------------------------------------------------
# _build_eval_expression
# ---------------------------------------------------------------------------
class TestBuildEvalExpression:
    def _opts(self, **overrides):
        base = {
            "language": "octave",
            "obj_name": "main",
            "sub_module": "main",
            "ref_module": "main",
            "weight": 1,
        }
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

    def test_function_mode_with_source_path_loads_the_script_first(self):
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="helper", args=(1,)),
            stem="sub",
            source_path="/t/it's/sub.m",
        )
        assert "source('/t/it''s/sub.m');" in expr
        assert expr.index("source(") < expr.index("helper(1);")

    def test_expression_has_try_catch_wrapper(self):
        """Uncaught Octave errors must surface as a nonzero exit
        code with the message on stderr.  Confirm the wrapper
        emits both."""
        expr = OctaveRuntime._build_eval_expression(self._opts(), stem="main")
        assert "try" in expr
        assert "addpath" not in expr
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

    def test_library_path_forwarded_for_nonstandard_installs(self, monkeypatch):
        monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/octave/lib")
        assert OctaveRuntime._safe_env()["LD_LIBRARY_PATH"] == "/opt/octave/lib"

    def test_octave_histfile_pinned_to_devnull(self):
        env = OctaveRuntime._safe_env()
        assert env["OCTAVE_HISTFILE"] == "/dev/null"

    def test_blas_threads_pinned_to_one(self):
        env = OctaveRuntime._safe_env()
        assert env["OPENBLAS_NUM_THREADS"] == "1"
        assert env["OMP_NUM_THREADS"] == "1"


# ---------------------------------------------------------------------------
# _tee_to_log
# ---------------------------------------------------------------------------
class TestTeeToLog:
    def test_writes_utf8_text(self):
        log = StringIO()
        OctaveRuntime._tee_to_log(b"hi there\n", log)
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
# _LAUNCHER
# ---------------------------------------------------------------------------
class TestLauncher:
    """The ``preexec_fn`` replacement: a stdlib-only Python script
    that applies the four rlimits and ``exec``s Octave in the same
    process (so ``proc.pid`` stays Octave's pid)."""

    def test_launcher_applies_limits_then_execs(self):
        """Run the real launcher: the exec'd child reports the rlimits
        it inherited, proving both the ``setrlimit`` calls and the
        ``os.execv`` hand-off work."""
        probe = (
            "import resource;"
            "print(resource.getrlimit(resource.RLIMIT_AS)[0]);"
            "print(resource.getrlimit(resource.RLIMIT_CPU)[0]);"
            "print(resource.getrlimit(resource.RLIMIT_FSIZE)[0]);"
            "print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])"
        )
        mem = 2 * 1024**3
        cpu = 30
        argv = [
            sys.executable,
            "-I",
            "-c",
            _LAUNCHER,
            str(mem),
            str(cpu),
            sys.executable,
            "-c",
            probe,
        ]
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, check=False
        )
        assert proc.returncode == 0, proc.stderr
        as_bytes, cpu_secs, fsize, nofile = (int(line) for line in proc.stdout.split())
        assert as_bytes == mem
        assert cpu_secs == cpu
        assert fsize == FILE_SIZE_LIMIT
        assert nofile == 256


# ---------------------------------------------------------------------------
# run() — subprocess mocked
# ---------------------------------------------------------------------------
class TestRunMocked:
    """Drive ``OctaveRuntime.run`` with a mocked ``subprocess.Popen``
    so we can exercise every branch of the process-management logic
    without needing GNU Octave installed."""

    def _opts(self, **overrides):
        base = {
            "language": "octave",
            "obj_name": "main",
            "sub_module": "main",
            "ref_module": "main",
            "weight": 1,
        }
        base.update(overrides)
        return Options(**base)

    def _resolve(self, tmp_path, name="main"):
        (tmp_path / f"{name}.m").write_text("disp('placeholder')\n")
        return str(tmp_path / f"{name}.m")

    def _mock_proc(self, out=b"", err=b"", rc=0):
        """Patch ``Popen``/``TemporaryFile``/``which``.

        Returns ``(stack, fake_proc, mock_popen)``; enter ``stack``
        as a context manager around the ``run`` call.  ``killpg`` is
        patched by default because ``run`` reaps the group on every
        exit path; tests that assert on it re-patch on top.
        """
        fake_proc = MagicMock()
        fake_proc.pid = 1234
        fake_proc.communicate.return_value = (None, None)
        fake_proc.returncode = rc
        stack = ExitStack()
        stack.enter_context(
            patch(
                "generic_grader.runtimes.octave.tempfile.TemporaryFile",
                side_effect=[BytesIO(out), BytesIO(err)],
            )
        )
        mock_popen = stack.enter_context(
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                return_value=fake_proc,
            )
        )
        stack.enter_context(
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            )
        )
        stack.enter_context(patch("generic_grader.runtimes.octave.os.killpg"))
        return stack, fake_proc, mock_popen

    def test_success_writes_stdout_to_log(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        stack, _fake_proc, mock_popen = self._mock_proc(out=b"hello\n")
        with stack:
            result = OctaveRuntime().run(options, handle, log, iter([]))

        assert isinstance(result, RuntimeResult)
        assert result.returned_values is None
        assert log.getvalue() == "hello\n"

        # Popen was called with the launcher argv shape we promised.
        argv = mock_popen.call_args.args[0]
        assert argv[0] == sys.executable
        assert argv[1:3] == ["-I", "-c"]
        assert argv[3] == _LAUNCHER
        assert argv[6] == "/usr/bin/octave"
        assert "--no-gui" in argv
        assert "--norc" in argv
        assert "--no-init-file" in argv
        assert "--quiet" in argv
        assert argv[-2] == "--eval"

        # No preexec_fn; limits come from the launcher, output from
        # TemporaryFile redirection instead of PIPEs.
        kwargs = mock_popen.call_args.kwargs
        assert "preexec_fn" not in kwargs
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] is subprocess.PIPE
        assert kwargs["stdout"] is not None
        assert kwargs["stderr"] is not None

    def test_run_builds_launcher_argv_from_options(self, fix_syspath):
        """The launcher receives ``mem_bytes`` and ``cpu_seconds``
        derived from ``Options`` before the Octave argv."""
        handle = self._resolve(fix_syspath)
        options = self._opts(memory_limit_GB=2.0, time_limit=7)
        stack, _fake_proc, mock_popen = self._mock_proc()
        with stack:
            OctaveRuntime().run(options, handle, StringIO(), iter([]))

        argv = mock_popen.call_args.args[0]
        assert argv[4] == str(2 * 1024**3)
        assert argv[5] == "8"  # int(time_limit) + 1

    def test_zero_memory_clamped_to_one_byte(self, fix_syspath):
        """A misconfigured test with ``memory_limit_GB=0`` must not
        pass ``0`` to ``RLIMIT_AS`` — the kernel would kill Octave
        before it starts.  The clamp to 1 byte still fails the run
        (Octave can't allocate) but cleanly."""
        handle = self._resolve(fix_syspath)
        options = self._opts(memory_limit_GB=0.0)
        stack, _fake_proc, mock_popen = self._mock_proc()
        with stack:
            OctaveRuntime().run(options, handle, StringIO(), iter([]))

        argv = mock_popen.call_args.args[0]
        assert argv[4] == "1"

    def test_win32_refused(self, fix_syspath):
        """The launcher mechanism is POSIX-only; keep the refusal."""
        handle = self._resolve(fix_syspath)
        options = self._opts()
        with (
            patch("generic_grader.runtimes.octave.sys.platform", "win32"),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
            pytest.raises(OctaveNotInstalledError, match="POSIX"),
        ):
            OctaveRuntime().run(options, handle, StringIO(), iter([]))

    def test_nonzero_exit_raises_octave_runtime_error(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        stack, _fake_proc, _ = self._mock_proc(
            out=b"partial output\n",
            err=b"error: undefined variable 'xyz'\n",
            rc=1,
        )
        with stack, pytest.raises(OctaveRuntimeError) as excinfo:
            OctaveRuntime().run(options, handle, log, iter([]))

        # Partial stdout still made it into the log.
        assert "partial output" in log.getvalue()
        # Stderr is attached for the student-facing hint.
        assert "undefined variable 'xyz'" in excinfo.value.stderr

    def test_output_overflow_raises_too_much_output(self, fix_syspath, monkeypatch):
        """A capture file at/over ``FILE_SIZE_LIMIT`` means the child
        hit the rlimit (Octave swallows SIGXFSZ and truncates), so
        overflow is detected by size, not by signal."""
        monkeypatch.setattr(octave_mod, "FILE_SIZE_LIMIT", 4)
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        stack, _fake_proc, _ = self._mock_proc(out=b"12345")
        with stack, pytest.raises(OctaveRuntimeError, match="too much output"):
            OctaveRuntime().run(options, handle, log, iter([]))

        # The oversized capture is not dumped into the log.
        assert log.getvalue() == ""

    def test_timeout_kills_process_group_and_raises(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts(time_limit=1)
        log = StringIO()

        stack, fake_proc, _ = self._mock_proc(out=b"partial\n")
        fake_proc.pid = 12345
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
        ]

        with (
            stack,
            patch("generic_grader.runtimes.octave.os.killpg") as mock_killpg,
            pytest.raises(OctaveTimeoutError, match="took longer than"),
        ):
            OctaveRuntime().run(options, handle, log, iter([]))

        # Process group was killed with SIGKILL, targeting the child pid.
        mock_killpg.assert_called_once()
        assert mock_killpg.call_args.args[0] == 12345

        # Partial stdout still made it into the log for the student.
        assert "partial" in log.getvalue()

    def test_timeout_output_overflow_raises_too_much_output(
        self, fix_syspath, monkeypatch
    ):
        """Overflow is detected on the timeout path too."""
        monkeypatch.setattr(octave_mod, "FILE_SIZE_LIMIT", 4)
        handle = self._resolve(fix_syspath)
        options = self._opts(time_limit=1)
        log = StringIO()

        stack, fake_proc, _ = self._mock_proc(out=b"12345")
        fake_proc.pid = 99
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
        ]

        with (
            stack,
            patch("generic_grader.runtimes.octave.os.killpg"),
            pytest.raises(OctaveRuntimeError, match="too much output"),
        ):
            OctaveRuntime().run(options, handle, log, iter([]))

    def test_timeout_error_wins_over_log_limit_error(self, fix_syspath):
        """``_tee_to_log`` on the timeout path may raise
        ``LogLimitExceededError``; the timeout error must win."""

        class LimitedLog:
            def write(self, data):
                raise LogLimitExceededError()

        handle = self._resolve(fix_syspath)
        options = self._opts(time_limit=1)

        stack, fake_proc, _ = self._mock_proc(out=b"partial\n")
        fake_proc.pid = 7
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
        ]

        with (
            stack,
            patch("generic_grader.runtimes.octave.os.killpg"),
            pytest.raises(OctaveTimeoutError),
        ):
            OctaveRuntime().run(options, handle, LimitedLog(), iter([]))

    def test_group_reaped_on_normal_exit(self, fix_syspath):
        """Even a clean exit reaps the process group (grandchildren
        from ``system()`` may outlive Octave); ``ProcessLookupError``
        (group already gone) is suppressed."""
        handle = self._resolve(fix_syspath)
        options = self._opts()

        stack, fake_proc, _ = self._mock_proc(out=b"ok\n")
        fake_proc.pid = 555
        with (
            stack,
            patch(
                "generic_grader.runtimes.octave.os.killpg",
                side_effect=ProcessLookupError,
            ) as mock_killpg,
        ):
            OctaveRuntime().run(options, handle, StringIO(), iter([]))

        mock_killpg.assert_called_once()
        assert mock_killpg.call_args.args[0] == 555

    def test_group_reaped_when_run_raises(self, fix_syspath):
        """Any exception escaping ``communicate`` still reaps the
        group on the way out."""
        handle = self._resolve(fix_syspath)
        options = self._opts()

        stack, fake_proc, _ = self._mock_proc()
        fake_proc.pid = 777
        fake_proc.communicate.side_effect = RuntimeError("boom")

        with (
            stack,
            patch("generic_grader.runtimes.octave.os.killpg") as mock_killpg,
            pytest.raises(RuntimeError, match="boom"),
        ):
            OctaveRuntime().run(options, handle, StringIO(), iter([]))

        mock_killpg.assert_called_once()
        assert mock_killpg.call_args.args[0] == 777

    def test_reap_group_never_signals_non_int_pid(self):
        """A non-int ``pid`` (an unconfigured ``MagicMock``) must never reach
        ``os.killpg``: ``killpg(1, sig)`` signals every permitted process."""
        fake_proc = MagicMock()
        with patch("generic_grader.runtimes.octave.os.killpg") as mock_killpg:
            OctaveRuntime._reap_group(fake_proc)

        mock_killpg.assert_not_called()
        fake_proc.wait.assert_called_once()

    def test_octave_not_on_path_raises(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        with (
            patch("generic_grader.runtimes.octave.shutil.which", return_value=None),
            pytest.raises(OctaveNotInstalledError, match="not"),
        ):
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
            pytest.raises(OctaveNotInstalledError, match="gone"),
        ):
            OctaveRuntime().run(options, handle, StringIO(), iter([]))

    def test_timeout_wait_expired_still_raises_timeout(self, fix_syspath):
        """If the post-kill ``wait`` also times out, we must still
        raise ``OctaveTimeoutError`` (not crash)."""
        handle = self._resolve(fix_syspath)
        options = self._opts(time_limit=1)
        log = StringIO()

        stack, fake_proc, _ = self._mock_proc()
        fake_proc.pid = 4242
        fake_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="octave", timeout=1),
        ]
        fake_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="octave", timeout=1)

        with (
            stack,
            patch("generic_grader.runtimes.octave.os.killpg"),
            pytest.raises(OctaveTimeoutError),
        ):
            OctaveRuntime().run(options, handle, log, iter([]))

    def test_stdin_is_piped_from_entries(self, fix_syspath):
        handle = self._resolve(fix_syspath)
        options = self._opts()
        log = StringIO()

        stack, fake_proc, mock_popen = self._mock_proc()
        with stack:
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
    """End-to-end tests that actually shell out to GNU Octave.

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

    def test_input_entries_read_end_to_end(self, fix_syspath):
        """``input('Num: ')`` in script mode reads a value piped from
        ``entries`` and prints the result."""
        (fix_syspath / "main.m").write_text("x = input('Num: ');\ndisp(x*2)\n")
        options = Options(
            language="octave",
            obj_name="main",
            sub_module="main",
            ref_module="main",
            weight=1,
        )
        log = StringIO()
        OctaveRuntime().run(
            options,
            str(fix_syspath / "main.m"),
            log,
            iter([42]),
        )
        assert "84" in log.getvalue()

    def test_memory_limit_is_enforced(self, fix_syspath):
        """A script allocating more than ``memory_limit_GB`` fails
        under ``RLIMIT_AS`` and surfaces as ``OctaveRuntimeError``."""
        (fix_syspath / "big.m").write_text("x = zeros(11000, 11000);\n")
        options = Options(
            language="octave",
            obj_name="big",
            sub_module="big",
            ref_module="big",
            memory_limit_GB=0.25,
            weight=1,
        )
        with pytest.raises(OctaveRuntimeError):
            OctaveRuntime().run(
                options,
                str(fix_syspath / "big.m"),
                StringIO(),
                iter([]),
            )

    def test_output_overflow_raises_too_much_output(self, fix_syspath, monkeypatch):
        """Octave survives SIGXFSZ (it installs its own handler) and
        writes past the rlimit are truncated, so overflow is detected
        by capture-file size against ``FILE_SIZE_LIMIT``."""
        monkeypatch.setattr(octave_mod, "FILE_SIZE_LIMIT", 4096)
        (fix_syspath / "spam.m").write_text(
            "for i = 1:2000; fprintf('%d\\n', i); end\n"
        )
        options = Options(
            language="octave",
            obj_name="spam",
            sub_module="spam",
            ref_module="spam",
            weight=1,
        )
        with pytest.raises(OctaveRuntimeError, match="too much output"):
            OctaveRuntime().run(
                options,
                str(fix_syspath / "spam.m"),
                StringIO(),
                iter([]),
            )

    def test_process_group_reaped_after_normal_exit(self, fix_syspath):
        """A script that backgrounds ``sleep 30`` and returns normally
        leaves no member of its process group behind."""
        (fix_syspath / "bg.m").write_text("system('sleep 30 &');\n")
        options = Options(
            language="octave",
            obj_name="bg",
            sub_module="bg",
            ref_module="bg",
            weight=1,
        )

        pids = []
        real_popen = subprocess.Popen

        def recording_popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            pids.append(proc.pid)
            return proc

        with patch(
            "generic_grader.runtimes.octave.subprocess.Popen",
            side_effect=recording_popen,
        ):
            OctaveRuntime().run(
                options,
                str(fix_syspath / "bg.m"),
                StringIO(),
                iter([]),
            )

        assert pids, "Popen was never called"
        deadline = time.monotonic() + 5
        while True:
            try:
                os.killpg(pids[0], 0)
            except ProcessLookupError:
                break
            assert time.monotonic() < deadline, "process group survived"
            time.sleep(0.05)


@pytest.mark.skipif(not _HAVE_OCTAVE, reason="GNU Octave not installed")
class TestFunctionModeStaging:
    """Function mode runs each file from a private copy so the
    reference and student never shadow each other, and can reach
    subfunctions that Octave hides from outside callers."""

    def _opts(self, obj_name, sub_module, ref_module="ref_none", **kw):
        return Options(
            language="octave",
            obj_name=obj_name,
            sub_module=sub_module,
            ref_module=ref_module,
            args=(3,),
            weight=1,
            **kw,
        )

    def _run(self, options, path):
        log = StringIO()
        OctaveRuntime().run(options, str(path), log, iter([]))
        return log.getvalue()

    def test_reference_file_does_not_run_student_code(self, fix_syspath):
        (fix_syspath / "foo.m").write_text(
            "function foo(x)\n  printf('student %d\\n', x);\nend\n"
        )
        (fix_syspath / "ref_foo.m").write_text(
            "function ref_foo(x)\n  printf('reference %d\\n', 2 * x);\nend\n"
        )
        options = self._opts("foo", "foo", "ref_foo")

        assert self._run(options, fix_syspath / "ref_foo.m") == "reference 6\n"
        assert self._run(options, fix_syspath / "foo.m") == "student 3\n"

    def test_subfunction_is_callable(self, fix_syspath):
        (fix_syspath / "sub.m").write_text(
            textwrap.dedent(
                """\
                function main_fn()
                  printf('main\\n');
                end
                function helper(x)
                  printf('helper %d\\n', 2 * x);
                end
                """
            )
        )
        options = self._opts("helper", "sub")
        assert self._run(options, fix_syspath / "sub.m") == "helper 6\n"

    def test_unterminated_subfunctions_get_a_hint(self, fix_syspath):
        (fix_syspath / "sub.m").write_text(
            "function main_fn()\n  printf('main\\n');\n"
            "function helper(x)\n  printf('helper\\n');\n"
        )
        options = self._opts("helper", "sub")
        with pytest.raises(OctaveRuntimeError) as excinfo:
            self._run(options, fix_syspath / "sub.m")
        assert "endfunction" in excinfo.value.stderr

    def test_sibling_helper_files_are_available(self, fix_syspath):
        (fix_syspath / "util_double.m").write_text(
            "function r = util_double(x)\n  r = 2 * x;\nend\n"
        )
        (fix_syspath / "foo.m").write_text(
            "function foo(x)\n  printf('%d\\n', util_double(x));\nend\n"
        )
        options = self._opts("foo", "foo")
        assert self._run(options, fix_syspath / "foo.m") == "6\n"

    def test_other_sides_file_is_not_copied(self, fix_syspath):
        (fix_syspath / "foo.m").write_text(
            "function foo(x)\n  printf('%d\\n', exist('ref_foo', 'file'));\nend\n"
        )
        (fix_syspath / "ref_foo.m").write_text("function ref_foo(x)\nend\n")
        options = self._opts("foo", "foo", "ref_foo")
        assert self._run(options, fix_syspath / "foo.m") == "0\n"

    def test_runs_in_a_private_directory_that_is_removed(self, fix_syspath):
        (fix_syspath / "foo.m").write_text(
            "function foo(x)\n  printf('%s\\n', pwd());\nend\n"
        )
        staged = []
        real_mkdtemp = octave_mod.tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            staged.append(path)
            return path

        with patch(
            "generic_grader.runtimes.octave.tempfile.mkdtemp",
            side_effect=recording_mkdtemp,
        ):
            out = self._run(self._opts("foo", "foo"), fix_syspath / "foo.m")

        assert len(staged) == 1
        assert out.strip() == os.path.realpath(staged[0])
        assert not os.path.exists(staged[0])

    def test_private_directory_removed_when_staging_fails(self, fix_syspath):
        (fix_syspath / "foo.m").write_text("function foo(x)\nend\n")
        staged = []
        real_mkdtemp = octave_mod.tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            staged.append(path)
            return path

        with (
            patch(
                "generic_grader.runtimes.octave.tempfile.mkdtemp",
                side_effect=recording_mkdtemp,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.copy2",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            self._run(self._opts("foo", "foo"), fix_syspath / "foo.m")

        assert staged
        assert not os.path.exists(staged[0])

    def test_private_directory_removed_when_octave_fails(self, fix_syspath):
        (fix_syspath / "foo.m").write_text("function foo(x)\n  error('nope');\nend\n")
        staged = []
        real_mkdtemp = octave_mod.tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            staged.append(path)
            return path

        with (
            patch(
                "generic_grader.runtimes.octave.tempfile.mkdtemp",
                side_effect=recording_mkdtemp,
            ),
            pytest.raises(OctaveRuntimeError),
        ):
            self._run(self._opts("foo", "foo"), fix_syspath / "foo.m")

        assert staged
        assert not os.path.exists(staged[0])


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
