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

import numpy as np
import pytest

from generic_grader.runtimes import octave as octave_mod
from generic_grader.runtimes.base import RuntimeResult
from generic_grader.runtimes.octave import (
    OCTAVE_EXECUTABLE,
    OctaveNotInstalledError,
    OctaveRuntime,
    OctaveRuntimeError,
    OctaveTimeoutError,
    _build_plot_capture_snippet,
    _decode_json_value,
    _decode_returned_values,
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
        """Without a sidecar, function mode emits the plain call —
        used by internal callers / tests that don't need to capture
        the return value."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="greet", args=("world",)),
            stem="greet",
        )
        assert "greet('world');" in expr
        # No sidecar path passed → no jsonencode wiring.
        assert "jsonencode" not in expr

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

    def test_function_mode_with_sidecar_wires_jsonencode(self):
        """When a sidecar path is passed we inject the capture harness:
        introspect ``nargout``, gather results into a cell, and
        ``jsonencode`` them to the file the parent can read after
        Octave exits."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="foo", args=(2,)),
            stem="foo",
            sidecar_path="/tmp/gg_octave_return_abc.json",
        )
        # The introspection line is there …
        assert "nargout('foo')" in expr
        # … varargout is treated as one output …
        assert "gg_nout__ < 0" in expr
        # … the call happens …
        assert "foo(2)" in expr
        # … and the JSON write goes to the exact path we passed.
        assert "'/tmp/gg_octave_return_abc.json'" in expr
        assert "jsonencode(gg_ret__)" in expr

    def test_sidecar_path_with_single_quote_is_escaped(self):
        """Octave single-quoted strings escape ``'`` by doubling it.
        A path containing a single quote (rare but possible in
        ``TMPDIR``) must not break the injected expression.  Requires
        function-mode (some ``args``) so the sidecar wiring is emitted."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="foo", args=(1,)),
            stem="foo",
            sidecar_path="/weird/it's/path.json",
        )
        assert "'/weird/it''s/path.json'" in expr

    def test_script_mode_ignores_sidecar(self):
        """Script mode has no single return value; even if a caller
        passes a sidecar path we don't emit the capture wiring."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="main"),
            stem="main",
            sidecar_path="/tmp/unused.json",
        )
        assert "jsonencode" not in expr
        assert "nargout" not in expr

    def test_plot_sidecar_injects_capture_and_toolkit(self):
        """When a plot sidecar path is supplied we prepend the
        headless-friendly ``graphics_toolkit`` header and append the
        capture snippet — both are gated on the presence of the path,
        so callers that don't need plot artifacts (older internal use)
        stay minimal."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="main"),
            stem="main",
            plot_sidecar_path="/tmp/gg_plot.json",
        )
        assert "graphics_toolkit('gnuplot')" in expr
        assert "DefaultFigureVisible" in expr
        assert "gg_plot_payload__" in expr
        assert "'/tmp/gg_plot.json'" in expr

    def test_plot_sidecar_off_by_default(self):
        """Without a plot sidecar path the toolkit header and capture
        snippet are suppressed — protecting the older callers /
        internal-use expressions that only want the return-value
        harness."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="main"),
            stem="main",
        )
        assert "graphics_toolkit" not in expr
        assert "gg_plot_payload__" not in expr

    def test_plot_sidecar_path_with_single_quote_is_escaped(self):
        """Same doubled-quote escape rule the return-value sidecar
        uses — a path containing a single quote still parses inside
        the injected fopen call."""
        expr = OctaveRuntime._build_eval_expression(
            self._opts(obj_name="main"),
            stem="main",
            plot_sidecar_path="/weird/it's/plot.json",
        )
        assert "'/weird/it''s/plot.json'" in expr


# ---------------------------------------------------------------------------
# _build_plot_capture_snippet
# ---------------------------------------------------------------------------
class TestBuildPlotCaptureSnippet:
    """Focused checks on the plot-capture Octave snippet.

    We don't try to fully mock Octave semantics here — the
    live-Octave integration tests below (and the plot-test end-to-end
    module in ``tests/image/``) do that.  These unit tests just
    confirm the snippet's shape so a regression in the string
    template is caught before it reaches an Octave subprocess.
    """

    def test_snippet_writes_to_provided_path(self):
        snippet = _build_plot_capture_snippet("/tmp/plot.json")
        assert "'/tmp/plot.json'" in snippet
        assert "jsonencode(gg_plot_payload__)" in snippet

    def test_snippet_skips_legend_axes(self):
        """Legend axes carry ``tag == 'legend'`` in Octave; the snippet
        must skip them so the primary drawing axes are the ones
        captured."""
        snippet = _build_plot_capture_snippet("/tmp/plot.json")
        assert "strcmp(get(gg_plot_ax__, 'tag'), 'legend')" in snippet

    def test_snippet_gathers_line_arrays(self):
        snippet = _build_plot_capture_snippet("/tmp/plot.json")
        assert "findobj(gg_plot_ax__, 'Type', 'line')" in snippet
        assert "get(gg_plot_lines__(gg_plot_li__), 'xdata')" in snippet
        assert "get(gg_plot_lines__(gg_plot_li__), 'ydata')" in snippet
        assert "get(gg_plot_lines__(gg_plot_li__), 'color')" in snippet

    def test_snippet_wraps_capture_in_try_catch(self):
        """A malformed figure must not fail an otherwise-passing run;
        the snippet's own ``try/catch`` swallows errors so the outer
        wrapper stays authoritative."""
        snippet = _build_plot_capture_snippet("/tmp/plot.json")
        assert snippet.strip().startswith("try")
        assert "end_try_catch" in snippet


# ---------------------------------------------------------------------------
# _read_plot_sidecar
# ---------------------------------------------------------------------------
class TestReadPlotSidecar:
    def test_missing_file_returns_none(self, tmp_path):
        assert OctaveRuntime._read_plot_sidecar(str(tmp_path / "nope.json")) is None

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        assert OctaveRuntime._read_plot_sidecar(str(p)) is None

    def test_whitespace_only_returns_none(self, tmp_path):
        p = tmp_path / "ws.json"
        p.write_text("   \n\t  ")
        assert OctaveRuntime._read_plot_sidecar(str(p)) is None

    def test_valid_json_returns_decoded_payload(self, tmp_path):
        p = tmp_path / "good.json"
        p.write_text('{"figures": [{"axes": []}]}')
        payload = OctaveRuntime._read_plot_sidecar(str(p))
        assert payload == {"figures": [{"axes": []}]}


# ---------------------------------------------------------------------------
# _decode_json_value + _decode_returned_values
# ---------------------------------------------------------------------------
class TestDecodeJsonValue:
    """Unit tests for the single-value decoder that maps JSON scalars
    to native Python types and JSON arrays to :class:`numpy.ndarray`.
    These run without touching Octave."""

    def test_none_passthrough(self):
        assert _decode_json_value(None) is None

    def test_int_passthrough(self):
        # ``json.loads('5')`` yields Python ``int``; must not be
        # coerced to a NumPy scalar.  ``type() is`` is deliberate:
        # ``isinstance(True, int)`` is True and would erase the
        # bool-vs-int distinction we're testing here and in
        # ``test_float_passthrough``.
        assert _decode_json_value(5) == 5
        assert type(_decode_json_value(5)) is int  # noqa: E721

    def test_float_passthrough(self):
        assert _decode_json_value(3.14) == 3.14
        assert type(_decode_json_value(3.14)) is float  # noqa: E721

    def test_bool_passthrough(self):
        assert _decode_json_value(True) is True
        assert _decode_json_value(False) is False

    def test_str_passthrough(self):
        assert _decode_json_value("hello world") == "hello world"

    def test_flat_list_becomes_ndarray(self):
        result = _decode_json_value([1.0, 2.0, 3.0])
        assert isinstance(result, np.ndarray)
        assert result.tolist() == [1.0, 2.0, 3.0]

    def test_nested_list_becomes_2d_ndarray(self):
        result = _decode_json_value([[1, 2], [3, 4]])
        assert isinstance(result, np.ndarray)
        assert result.shape == (2, 2)

    def test_empty_list_becomes_empty_ndarray(self):
        result = _decode_json_value([])
        assert isinstance(result, np.ndarray)
        assert result.size == 0


class TestDecodeReturnedValues:
    """Unit tests for the top-level decoder that unwraps the sidecar
    array by ``nargout`` — zero → ``None``, one → bare value, two or
    more → tuple."""

    def test_empty_array_is_none(self):
        assert _decode_returned_values("[]") is None

    def test_single_element_unwrapped(self):
        assert _decode_returned_values("[42]") == 42
        # And it stays a plain int, not a 1-tuple.
        assert not isinstance(_decode_returned_values("[42]"), tuple)

    def test_multiple_elements_become_tuple(self):
        result = _decode_returned_values('[1, 2, "hi"]')
        assert result == (1, 2, "hi")
        assert isinstance(result, tuple)

    def test_accepts_already_parsed_list(self):
        """The helper is also usable with an in-memory list — e.g.
        from ``json.load`` directly on a file handle."""
        assert _decode_returned_values([1, 2]) == (1, 2)

    def test_bytes_payload(self):
        """Reading the sidecar as bytes must decode identically to
        reading as text — lets callers avoid an explicit ``decode``
        step."""
        assert _decode_returned_values(b"[10]") == 10

    def test_non_array_payload_raises_valueerror(self):
        with pytest.raises(ValueError, match="must be a JSON array"):
            _decode_returned_values("42")

    def test_scalar_wrapped_in_array_stays_scalar(self):
        """Octave scalar returns come through as a 1-element JSON
        array — the unwrap makes them a bare Python value."""
        assert _decode_returned_values("[3.14]") == 3.14

    def test_vector_wrapped_in_array_becomes_ndarray(self):
        result = _decode_returned_values("[[1, 2, 3]]")
        assert isinstance(result, np.ndarray)
        assert result.tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# _read_sidecar
# ---------------------------------------------------------------------------
class TestReadSidecar:
    def test_none_path_returns_none(self):
        assert OctaveRuntime._read_sidecar(None) is None

    def test_missing_file_returns_none(self, tmp_path):
        """If Octave never got to the write — e.g. it crashed before
        the ``jsonencode`` line — we treat the return value as
        absent rather than surfacing a filesystem error."""
        missing = tmp_path / "does-not-exist.json"
        assert OctaveRuntime._read_sidecar(str(missing)) is None

    def test_empty_file_returns_none(self, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text("")
        assert OctaveRuntime._read_sidecar(str(empty)) is None

    def test_whitespace_only_returns_none(self, tmp_path):
        blank = tmp_path / "blank.json"
        blank.write_text("   \n\t")
        assert OctaveRuntime._read_sidecar(str(blank)) is None

    def test_valid_payload_decoded(self, tmp_path):
        sidecar = tmp_path / "ok.json"
        sidecar.write_text("[7]")
        assert OctaveRuntime._read_sidecar(str(sidecar)) == 7

    def test_malformed_json_raises_octave_runtime_error(self, tmp_path):
        """A corrupt sidecar (e.g. Octave printed something on the
        wrong stream) should surface as an :class:`OctaveRuntimeError`
        so ``__User__.call_obj`` renders it like any other Octave
        error — not as a bare :class:`json.JSONDecodeError`."""
        bad = tmp_path / "bad.json"
        bad.write_text("{not-json")
        with pytest.raises(OctaveRuntimeError) as excinfo:
            OctaveRuntime._read_sidecar(str(bad))
        assert "decode" in str(excinfo.value).lower()

    def test_non_array_payload_raises_octave_runtime_error(self, tmp_path):
        """``_decode_returned_values`` rejects non-arrays with
        :class:`ValueError`; ``_read_sidecar`` must translate that
        into the language-appropriate runtime error."""
        bad = tmp_path / "bad.json"
        bad.write_text('"scalar string, not an array"')
        with pytest.raises(OctaveRuntimeError):
            OctaveRuntime._read_sidecar(str(bad))


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

    def test_function_mode_reads_and_deletes_sidecar(self, fix_syspath):
        """With ``args`` set, the runtime allocates a sidecar path,
        threads it into the eval expression, and — after Octave
        ‘exits’ — decodes the file into ``returned_values`` and
        deletes the file.  We simulate Octave writing the sidecar by
        intercepting ``Popen`` and doing the write ourselves in the
        stub's ``communicate``."""
        handle = self._resolve(fix_syspath)
        options = self._opts(args=(2,))
        log = StringIO()

        # Capture the sidecar path so we can (a) write the payload
        # from the stub, and (b) verify the parent unlinked it after
        # ``run`` returned.
        captured_paths = []

        def fake_popen(argv, **kwargs):
            # The sidecar path is embedded in the --eval argument.
            eval_expr = argv[argv.index("--eval") + 1]
            # Extract the path between the first pair of single quotes
            # after ``fopen(``.
            marker = "fopen('"
            start = eval_expr.index(marker) + len(marker)
            end = eval_expr.index("'", start)
            path = eval_expr[start:end]
            # Undo the ``''`` → ``'`` escape.
            path = path.replace("''", "'")
            captured_paths.append(path)
            # Simulate Octave writing the JSON payload before exit.
            with open(path, "w", encoding="utf-8") as sidecar:
                sidecar.write("[8]")
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            return proc

        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                side_effect=fake_popen,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
        ):
            result = OctaveRuntime().run(options, handle, log, iter([]))

        assert result.returned_values == 8
        # Sidecar path was captured …
        assert len(captured_paths) == 1
        # … and cleaned up by the ``finally`` in ``run``.
        assert not os.path.exists(captured_paths[0])

    def test_function_mode_uses_isolated_directory(self, fix_syspath):
        """Function-mode ``run`` must copy the resolved ``.m`` file
        into a private per-invocation directory renamed to
        ``<obj_name>.m`` and use that directory as the subprocess
        ``cwd``.  This is what makes the ``@reference_test`` swap
        correct for Octave: ref and student files can coexist in the
        submission directory (as ``ref_foo.m`` and ``foo.m``) yet
        each subprocess only ever sees one of them, resolved by
        ``obj_name`` — so Octave's file-stem-based function lookup
        can never pick the wrong one.
        """
        # Write a ref-style handle whose stem differs from obj_name.
        ref_path = fix_syspath / "ref_foo.m"
        ref_path.write_text("function y = foo(x)\n  y = x + 1;\nendfunction\n")
        options = self._opts(obj_name="foo", args=(1,))
        log = StringIO()

        seen_cwd = []
        seen_files = []

        def fake_popen(argv, **kwargs):
            cwd = kwargs["cwd"]
            seen_cwd.append(cwd)
            # Snapshot the isolated directory's contents *while* the
            # subprocess would be running — before the ``finally``
            # cleanup runs — to prove the copy happened.
            seen_files.append(sorted(os.listdir(cwd)))
            # Also simulate Octave writing an empty sidecar so the
            # decode path treats the call as returning nothing.
            eval_expr = argv[argv.index("--eval") + 1]
            marker = "fopen('"
            start = eval_expr.index(marker) + len(marker)
            end = eval_expr.index("'", start)
            path = eval_expr[start:end].replace("''", "'")
            with open(path, "w", encoding="utf-8") as f:
                f.write("[]")
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            return proc

        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                side_effect=fake_popen,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
        ):
            OctaveRuntime().run(options, str(ref_path), log, iter([]))

        assert len(seen_cwd) == 1
        isolated_dir = seen_cwd[0]
        # cwd must be *not* the submission directory — that's the
        # whole point of the copy — and must contain a
        # ``<obj_name>.m`` file whose contents came from ``ref_foo.m``.
        assert isolated_dir != str(fix_syspath)
        assert seen_files[0] == ["foo.m"]
        # The isolated directory should be cleaned up on return.
        assert not os.path.exists(isolated_dir)

    def test_sidecar_cleanup_survives_missing_file(self, fix_syspath):
        """If Octave crashes so hard the sidecar file never gets
        written, ``run`` still tries to unlink it — the resulting
        :class:`FileNotFoundError` must be swallowed so the original
        error is what the caller sees."""
        handle = self._resolve(fix_syspath)
        options = self._opts(args=(1,))
        log = StringIO()

        fake_proc = MagicMock()
        fake_proc.communicate.return_value = (b"", b"boom\n")
        fake_proc.returncode = 1

        # Delete the sidecar out from under ``run`` between its
        # allocation and the ``finally`` cleanup by patching unlink.
        with (
            patch(
                "generic_grader.runtimes.octave.subprocess.Popen",
                return_value=fake_proc,
            ),
            patch(
                "generic_grader.runtimes.octave.shutil.which",
                return_value="/usr/bin/octave",
            ),
            patch(
                "generic_grader.runtimes.octave.os.unlink",
                side_effect=FileNotFoundError,
            ),
        ):
            # The primary error — OctaveRuntimeError from nonzero exit
            # — must not be masked by the cleanup exception.
            with pytest.raises(OctaveRuntimeError):
                OctaveRuntime().run(options, handle, log, iter([]))


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

    def test_function_mode_captures_scalar_return_value(self, fix_syspath):
        """End-to-end: an Octave function returning a scalar shows up
        as a plain Python ``float`` on ``RuntimeResult.returned_values``
        — which is exactly the shape the
        ``function_return_values_match_reference`` test compares."""
        (fix_syspath / "double_it.m").write_text(
            textwrap.dedent(
                """\
                function y = double_it(x)
                  y = x * 2;
                end
                """
            )
        )
        options = Options(
            language="octave",
            obj_name="double_it",
            sub_module="double_it",
            ref_module="double_it",
            args=(21,),
            weight=1,
        )
        result = OctaveRuntime().run(
            options,
            str(fix_syspath / "double_it.m"),
            StringIO(),
            iter([]),
        )
        # Octave's ``jsonencode`` emits doubles for numeric scalars, so
        # we compare with equality against the numeric value — the
        # exact type check happens in the decoder unit tests above.
        assert result.returned_values == 42

    def test_function_mode_captures_vector_return_value(self, fix_syspath):
        """A row vector returned from Octave round-trips as a NumPy
        1-D array — the same shape a Python reference returning
        ``np.arange(1, n+1)`` would produce."""
        (fix_syspath / "range_of.m").write_text(
            textwrap.dedent(
                """\
                function v = range_of(n)
                  v = 1:n;
                end
                """
            )
        )
        options = Options(
            language="octave",
            obj_name="range_of",
            sub_module="range_of",
            ref_module="range_of",
            args=(4,),
            weight=1,
        )
        result = OctaveRuntime().run(
            options,
            str(fix_syspath / "range_of.m"),
            StringIO(),
            iter([]),
        )
        assert isinstance(result.returned_values, np.ndarray)
        assert result.returned_values.tolist() == [1, 2, 3, 4]

    def test_function_mode_captures_multiple_return_values(self, fix_syspath):
        """``[a, b] = f(x)`` in Octave becomes ``(a, b)`` in Python,
        matching Python's own multiple-return convention."""
        (fix_syspath / "pair.m").write_text(
            textwrap.dedent(
                """\
                function [a, b] = pair(x)
                  a = x;
                  b = x + 1;
                end
                """
            )
        )
        options = Options(
            language="octave",
            obj_name="pair",
            sub_module="pair",
            ref_module="pair",
            args=(9,),
            weight=1,
        )
        result = OctaveRuntime().run(
            options,
            str(fix_syspath / "pair.m"),
            StringIO(),
            iter([]),
        )
        assert result.returned_values == (9, 10)

    def test_function_mode_void_function_gives_none(self, fix_syspath):
        """A function with no output arguments — ``nargout == 0`` —
        yields ``None`` (Python's convention for ‘no explicit
        return’).  The sidecar payload is an empty JSON array."""
        (fix_syspath / "printer.m").write_text(
            textwrap.dedent(
                """\
                function printer(x)
                  fprintf('got %d\\n', x);
                end
                """
            )
        )
        options = Options(
            language="octave",
            obj_name="printer",
            sub_module="printer",
            ref_module="printer",
            args=(5,),
            weight=1,
        )
        log = StringIO()
        result = OctaveRuntime().run(
            options,
            str(fix_syspath / "printer.m"),
            log,
            iter([]),
        )
        assert result.returned_values is None
        assert "got 5" in log.getvalue()

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

    def test_function_mode_ref_and_sub_isolated_from_shared_dir(self, fix_syspath):
        """Live end-to-end check for the isolation the mocked test
        above documents: two ``.m`` files coexist in the same
        directory but define the *same* function name differently,
        and each ``run`` invocation resolves to the file it was
        pointed at — not to whichever one happens to share Octave's
        function-lookup priority.

        This is the exact scenario ``@reference_test`` produces, and
        it's what would silently break the ``function/*`` test types
        under Octave if the runtime didn't run each file from a
        private CWD.
        """
        (fix_syspath / "double_it.m").write_text(
            "function y = double_it(x)\n  y = x * 3;\nendfunction\n"
        )
        (fix_syspath / "ref_double_it.m").write_text(
            "function y = double_it(x)\n  y = x * 2;\nendfunction\n"
        )
        options = Options(
            language="octave",
            obj_name="double_it",
            sub_module="double_it",
            ref_module="ref_double_it",
            args=(21,),
            weight=1,
        )

        # Run the reference file explicitly; must return 42.
        ref_result = OctaveRuntime().run(
            options, str(fix_syspath / "ref_double_it.m"), StringIO(), iter([])
        )
        assert ref_result.returned_values == 42

        # Run the submission file explicitly; must return 63.
        sub_result = OctaveRuntime().run(
            options, str(fix_syspath / "double_it.m"), StringIO(), iter([])
        )
        assert sub_result.returned_values == 63


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
