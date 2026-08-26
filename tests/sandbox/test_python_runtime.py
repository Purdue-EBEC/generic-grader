"""Tests for the in-process Python runtime worker.

These tests exercise `run_request` directly, without spawning a real
sandboxed subprocess. The isolate-based runner (commit 4) calls the
same `run_request` from inside the sandbox, so the contract tested
here is exactly what the host sees over the wire.
"""

import os
import textwrap
from pathlib import Path

import pytest

from generic_grader.sandbox.protocol import Request, Response
from generic_grader.sandbox.python_runtime import _is_grader_frame, run_request

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def submission_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clean directory to hold a single test submission module.

    Each test writes its own module file into this directory and passes
    the path to `run_request` via the `submission_dir` Request field.
    """
    # Make sure no stale import cache references a module with the same
    # name from a previous test.
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    return tmp_path


def _write(submission_dir: Path, name: str, source: str) -> None:
    (submission_dir / name).write_text(textwrap.dedent(source))


def _request(
    submission_dir: Path,
    module: str = "submission",
    obj_name: str = "main",
    **overrides,
) -> Request:
    base = dict(
        runtime="python",
        submission_dir=str(submission_dir),
        module=module,
        obj_name=obj_name,
    )
    base.update(overrides)
    return Request(**base)


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def test_run_request_returns_response_instance(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 42
        """,
    )
    resp = run_request(_request(submission_dir))
    assert isinstance(resp, Response)
    assert resp.exception is None


def test_run_request_captures_return_value(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 42
        """,
    )
    resp = run_request(_request(submission_dir))
    returns = [e for e in resp.events if e.type == "return"]
    assert len(returns) == 1
    assert returns[0].value == 42


def test_run_request_passes_args_and_kwargs(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main(a, b, *, scale=1):
            return (a + b) * scale
        """,
    )
    resp = run_request(_request(submission_dir, args=(3, 4), kwargs={"scale": 10}))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == 70


# ---------------------------------------------------------------------------
# stdout / stderr capture
# ---------------------------------------------------------------------------


def test_run_request_captures_stdout(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            print("hello")
            print("world")
        """,
    )
    resp = run_request(_request(submission_dir))
    stdout_text = "".join(e.data for e in resp.events if e.type == "stdout")
    assert stdout_text == "hello\nworld\n"


def test_run_request_captures_stderr(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        import sys
        def main():
            sys.stderr.write("oops\\n")
        """,
    )
    resp = run_request(_request(submission_dir))
    stderr_text = "".join(e.data for e in resp.events if e.type == "stderr")
    assert "oops" in stderr_text


def test_run_request_preserves_stdout_order_relative_to_stdin(submission_dir):
    """stdout prompts and stdin entries interleave in the order they happen."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            a = input("first? ")
            b = input("second? ")
            return a + b
        """,
    )
    resp = run_request(_request(submission_dir, entries=("X", "Y")))
    types = [e.type for e in resp.events if e.type in ("stdout", "stdin", "return")]
    # Expect: stdout("first? "), stdin("X"), stdout("second? "), stdin("Y"), return
    assert types == ["stdout", "stdin", "stdout", "stdin", "return"]
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == "XY"


# ---------------------------------------------------------------------------
# stdin / input() handling
# ---------------------------------------------------------------------------


def test_run_request_input_pulls_from_entries(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            name = input("name? ")
            return f"hi {name}"
        """,
    )
    resp = run_request(_request(submission_dir, entries=("Alice",)))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == "hi Alice"
    stdins = [e for e in resp.events if e.type == "stdin"]
    assert [e.data for e in stdins] == ["Alice"]


def test_run_request_input_emits_eof_when_entries_exhausted(submission_dir):
    """Running out of entries should surface as an EOFError in the chain.

    The internal StopIteration that drives the responder must NOT leak
    into the serialized exception chain -- real CPython ``input()``
    raises a bare EOFError, and the grader's existing exception
    classification (importer.py walks ``__cause__``/``__context__``)
    would be confused by a chained StopIteration.
    """
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return input("more? ")
        """,
    )
    resp = run_request(_request(submission_dir, entries=()))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "EOFError"
    # No StopIteration in the chain -- we raise ``from None``.
    assert all(link["type"] != "StopIteration" for link in resp.exception)


def test_run_request_reports_unused_entries(submission_dir):
    """If the student returns before consuming all entries, host needs to know."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            input("first ")
            return "done"
        """,
    )
    resp = run_request(_request(submission_dir, entries=("a", "b", "c")))
    # One entry consumed leaves two leftover.
    extras = [e for e in resp.events if e.type == "unused_entries"]
    assert len(extras) == 1
    assert extras[0].count == 2


# ---------------------------------------------------------------------------
# Exception chain (filtered to student frames only)
# ---------------------------------------------------------------------------


def test_run_request_exception_chain_includes_type_and_message(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            raise ValueError("bad number")
        """,
    )
    resp = run_request(_request(submission_dir))
    assert resp.exception is not None
    chain = resp.exception
    assert chain[0]["type"] == "ValueError"
    assert chain[0]["message"] == "bad number"


def test_run_request_exception_traceback_includes_student_file(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def helper():
            raise ZeroDivisionError("oh no")

        def main():
            helper()
        """,
    )
    resp = run_request(_request(submission_dir))
    tb = resp.exception[0]["traceback"]
    assert "submission.py" in tb
    # `helper` lives in the student file too.
    assert "helper" in tb


def test_run_request_exception_traceback_omits_grader_frames(submission_dir):
    """Grader frames (worker, runtime) must not leak to the student.

    The worker invokes the student callable through its own machinery,
    so the raw traceback contains worker frames. Those frames live
    inside `generic_grader`; they must be scrubbed from the serialized
    traceback before it crosses the wire.
    """
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            raise RuntimeError("oh no")
        """,
    )
    resp = run_request(_request(submission_dir))
    tb = resp.exception[0]["traceback"]
    assert "generic_grader" not in tb
    assert "python_runtime" not in tb


def test_run_request_exception_chain_preserves_cause(submission_dir):
    """Chained exceptions (`raise X from Y`) must show both links."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            try:
                int("not a number")
            except ValueError as e:
                raise RuntimeError("wrap") from e
        """,
    )
    resp = run_request(_request(submission_dir))
    types = [link["type"] for link in resp.exception]
    assert "RuntimeError" in types
    assert "ValueError" in types


def test_run_request_exception_chain_preserves_implicit_context(submission_dir):
    """`__context__` (no explicit `from`) should still surface in the chain."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            try:
                int("not a number")
            except ValueError:
                raise RuntimeError("wrap")
        """,
    )
    resp = run_request(_request(submission_dir))
    types = [link["type"] for link in resp.exception]
    assert "RuntimeError" in types
    assert "ValueError" in types


# ---------------------------------------------------------------------------
# Import phase vs call phase
# ---------------------------------------------------------------------------


def test_run_request_marks_phase_for_import_failure(submission_dir):
    """If the module fails to import, phase should be 'import'."""
    _write(
        submission_dir,
        "submission.py",
        """
        raise SyntaxError("broken at module level")
        """,
    )
    resp = run_request(_request(submission_dir))
    assert resp.exception is not None
    phases = [e for e in resp.events if e.type == "phase"]
    assert phases[-1].name == "import"


def test_run_request_marks_phase_for_call_failure(submission_dir):
    """If the call raises, phase should be 'call'."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            raise ValueError("bad")
        """,
    )
    resp = run_request(_request(submission_dir))
    phases = [e for e in resp.events if e.type == "phase"]
    assert phases[-1].name == "call"


def test_run_request_phase_completed_on_success(submission_dir):
    """Success path emits a final phase=='completed'."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return None
        """,
    )
    resp = run_request(_request(submission_dir))
    phases = [e for e in resp.events if e.type == "phase"]
    assert phases[-1].name == "completed"


def test_run_request_module_missing_is_import_phase(submission_dir):
    """A missing module raises ModuleNotFoundError in the import phase."""
    resp = run_request(_request(submission_dir, module="not_real"))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "ModuleNotFoundError"
    phases = [e for e in resp.events if e.type == "phase"]
    assert phases[-1].name == "import"


def test_run_request_obj_missing_is_import_phase(submission_dir):
    """A missing attribute on an otherwise-good module is still import-phase."""
    _write(
        submission_dir,
        "submission.py",
        """
        def something_else():
            pass
        """,
    )
    resp = run_request(_request(submission_dir, obj_name="main"))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "AttributeError"
    phases = [e for e in resp.events if e.type == "phase"]
    assert phases[-1].name == "import"


# ---------------------------------------------------------------------------
# Captures whitelist
# ---------------------------------------------------------------------------


def test_run_request_captures_can_skip_stdout(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            print("noisy")
            return 1
        """,
    )
    resp = run_request(_request(submission_dir, captures=("return", "exception")))
    assert not any(e.type == "stdout" for e in resp.events)
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == 1


def test_run_request_captures_can_skip_return(submission_dir):
    """If 'return' is not in captures, no return event is emitted."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 99
        """,
    )
    resp = run_request(_request(submission_dir, captures=("stdout", "exception")))
    assert not any(e.type == "return" for e in resp.events)


# ---------------------------------------------------------------------------
# Return value JSON-safety
# ---------------------------------------------------------------------------


def test_run_request_non_serializable_return_value_uses_repr(submission_dir):
    """Custom objects can't go over the wire; fall back to repr()."""
    _write(
        submission_dir,
        "submission.py",
        """
        class Widget:
            def __repr__(self):
                return "<Widget id=7>"

        def main():
            return Widget()
        """,
    )
    resp = run_request(_request(submission_dir))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].non_serializable is True
    assert returns[0].repr == "<Widget id=7>"


def test_run_request_serializable_return_value_does_not_set_repr_flag(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return {"answer": 42, "items": [1, 2, 3]}
        """,
    )
    resp = run_request(_request(submission_dir))
    ret_event = next(e for e in resp.events if e.type == "return")
    assert ret_event.value == {"answer": 42, "items": [1, 2, 3]}
    assert "non_serializable" not in ret_event.extra


# ---------------------------------------------------------------------------
# fixed_time
# ---------------------------------------------------------------------------


def test_run_request_fixed_time_freezes_clock(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        from datetime import datetime
        def main():
            return datetime.now().isoformat()
        """,
    )
    resp = run_request(_request(submission_dir, fixed_time="2025-01-01 12:00:00"))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value.startswith("2025-01-01T12:00:00")


# ---------------------------------------------------------------------------
# Elapsed time
# ---------------------------------------------------------------------------


def test_run_request_records_elapsed_seconds(submission_dir):
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 1
        """,
    )
    resp = run_request(_request(submission_dir))
    assert resp.elapsed_seconds >= 0.0


# ---------------------------------------------------------------------------
# Working directory and sys.path isolation
# ---------------------------------------------------------------------------


def test_run_request_uses_submission_dir_as_cwd(submission_dir):
    """Files created at relative paths must land inside the submission dir."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            with open("hello.txt", "w") as f:
                f.write("ok")
            return "written"
        """,
    )
    run_request(_request(submission_dir))
    assert (submission_dir / "hello.txt").is_file()
    assert (submission_dir / "hello.txt").read_text() == "ok"
    # Worker must restore cwd on the way out so the host process is unaffected.
    assert os.getcwd() != str(submission_dir)


def test_run_request_restores_sys_path_and_modules(submission_dir):
    """After a run, sys.path and sys.modules should not retain the submission."""
    import sys

    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 1
        """,
    )
    before_path = list(sys.path)
    before_modules = set(sys.modules)
    run_request(_request(submission_dir))
    assert sys.path == before_path
    assert "submission" not in (set(sys.modules) - before_modules)


# ---------------------------------------------------------------------------
# matplotlib fallbacks when matplotlib is unavailable
# ---------------------------------------------------------------------------


def test_run_request_survives_missing_figure_serializer(submission_dir, monkeypatch):
    """If the figure serializer can't be imported, the worker still returns.

    This is the path the eventual Octave runtime will hit -- it shares
    the worker scaffolding but ships without matplotlib.
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "generic_grader.sandbox.figure_serializer":
            raise ImportError("simulated missing matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 1
        """,
    )
    resp = run_request(_request(submission_dir))
    assert resp.exception is None
    # No figure events because the serializer couldn't load.
    assert not any(e.type == "figure" for e in resp.events)


def test_run_request_survives_missing_pyplot_when_figures_disabled(
    submission_dir, monkeypatch
):
    """The 'close figures' fallback also tolerates missing matplotlib."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib.pyplot":
            raise ImportError("simulated missing matplotlib")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 1
        """,
    )
    # 'figures' not in captures -> worker tries to close pyplot figures
    # as cleanup; that import must be tolerated.
    resp = run_request(_request(submission_dir, captures=("return", "exception")))
    assert resp.exception is None


# ---------------------------------------------------------------------------
# _is_grader_frame helper
# ---------------------------------------------------------------------------


def test_is_grader_frame_empty_filename():
    """Frames synthesized by `exec` may carry an empty filename."""
    assert _is_grader_frame("") is False


def test_is_grader_frame_unresolvable_path(monkeypatch):
    """Path.resolve() raising must not crash the serializer."""
    from pathlib import Path as _Path

    original_resolve = _Path.resolve

    def boom(self, *args, **kwargs):
        raise OSError("cannot resolve")

    monkeypatch.setattr(_Path, "resolve", boom)
    try:
        # Should fall back to the raw filename without raising.
        assert _is_grader_frame("/some/student/path.py") is False
    finally:
        monkeypatch.setattr(_Path, "resolve", original_resolve)


def test_run_request_two_modules_with_same_name_do_not_share_state(
    submission_dir, tmp_path
):
    """Two consecutive runs with different submission dirs must not alias."""
    other = tmp_path / "other"
    other.mkdir()
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return "first"
        """,
    )
    _write(
        other,
        "submission.py",
        """
        def main():
            return "second"
        """,
    )
    r1 = run_request(_request(submission_dir))
    r2 = run_request(_request(other))
    v1 = next(e for e in r1.events if e.type == "return").value
    v2 = next(e for e in r2.events if e.type == "return").value
    assert v1 == "first"
    assert v2 == "second"


# ---------------------------------------------------------------------------
# Defensive input validation
# ---------------------------------------------------------------------------


def test_run_request_rejects_invalid_module_name(submission_dir):
    """Worker won't pass arbitrary strings to ``importlib.import_module``.

    Defense in depth: the host always constructs valid identifiers,
    but tests call ``run_request`` directly and the worker shouldn't
    silently accept a malformed module name.
    """
    resp = run_request(_request(submission_dir, module="bad/path.py"))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "ValueError"
    assert "module name" in resp.exception[0]["message"].lower()


def test_run_request_rejects_invalid_obj_name(submission_dir):
    """Same guard applies to the attribute name lookup."""
    _write(submission_dir, "submission.py", "def main():\n    return None\n")
    resp = run_request(_request(submission_dir, obj_name="main; rm -rf /"))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "ValueError"
    assert "object name" in resp.exception[0]["message"].lower()


def test_run_request_accepts_dotted_module_name(submission_dir):
    """Dotted package paths remain valid."""
    pkg = submission_dir / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    _write(pkg, "submission.py", "def main():\n    return 42\n")
    resp = run_request(_request(submission_dir, module="mypkg.submission"))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == 42


# ---------------------------------------------------------------------------
# Exception-chain depth cap
# ---------------------------------------------------------------------------


def test_exception_chain_capped_at_max_links():
    """Chains longer than the cap are truncated, not infinite-looped."""
    from generic_grader.sandbox.python_runtime import (
        _MAX_EXCEPTION_CHAIN_LINKS,
        _serialize_exception_chain,
    )

    # Build a chain longer than the cap.
    root = ValueError("root")
    head: BaseException = root
    for i in range(_MAX_EXCEPTION_CHAIN_LINKS + 5):
        try:
            raise RuntimeError(f"link {i}") from head
        except RuntimeError as e:
            head = e

    chain = _serialize_exception_chain(head)
    assert len(chain) == _MAX_EXCEPTION_CHAIN_LINKS


# ---------------------------------------------------------------------------
# PatchSpec reconstruction (commit 5b)
# ---------------------------------------------------------------------------


from generic_grader.sandbox.protocol import PatchSpec  # noqa: E402
from generic_grader.sandbox.python_runtime import (  # noqa: E402
    _build_mock_from_spec,
    _enter_patches_from_specs,
    _resolve_error_class,
    _target_basename,
)


def test_target_basename_strips_dotted_prefix():
    assert _target_basename("submission.input") == "input"
    assert _target_basename("a.b.c.func") == "func"


def test_resolve_error_class_returns_exception_subclass():
    from generic_grader.utils.exceptions import ExitError

    resolved = _resolve_error_class("generic_grader.utils.exceptions.ExitError")
    assert resolved is ExitError


def test_resolve_error_class_rejects_malformed_qualname():
    with pytest.raises(ValueError, match="Invalid error_qualname"):
        _resolve_error_class("not-a-qualname")


def test_resolve_error_class_rejects_non_exception():
    """Anything other than a BaseException subclass is rejected."""
    # `os.path` resolves but is a module, not an exception class.
    with pytest.raises(TypeError, match="not an exception class"):
        _resolve_error_class("os.path")


def test_build_mock_from_spec_noop_returns_none_and_swallows_args():
    spec = PatchSpec(target="submission.do_thing", kind="noop")
    mock = _build_mock_from_spec(spec)
    assert mock() is None
    assert mock(1, 2, k=3) is None


def test_build_mock_from_spec_iter_returns_values_then_raises():
    from generic_grader.utils.exceptions import ExcessFunctionCallError

    spec = PatchSpec(target="submission.input", kind="iter_returns", values=["a", "b"])
    mock = _build_mock_from_spec(spec)
    assert mock() == "a"
    assert mock("ignored prompt") == "b"
    with pytest.raises(ExcessFunctionCallError):
        mock()


def test_build_mock_from_spec_raise_error_raises_with_call_str():
    from generic_grader.utils.exceptions import ExitError

    spec = PatchSpec(
        target="builtins.exit",
        kind="raise_error",
        error_qualname="generic_grader.utils.exceptions.ExitError",
    )
    mock = _build_mock_from_spec(spec)
    with pytest.raises(ExitError) as exc_info:
        mock(1, key="val")
    assert "exit" in str(exc_info.value)


def test_build_mock_from_spec_source_execs_in_empty_namespace():
    src = textwrap.dedent(
        """
        def fake_falling_dist(time):
            return (time * 1234567.89) % 125
        """
    )
    spec = PatchSpec(
        target="submission.falling_dist",
        kind="source",
        source=src,
        name="fake_falling_dist",
    )
    mock = _build_mock_from_spec(spec)
    # Pure-arithmetic body works without any host globals leaking in.
    assert mock(0) == 0.0
    assert mock(2) == (2 * 1234567.89) % 125


def test_build_mock_from_spec_source_rejects_missing_name():
    """If the source doesn't define a callable matching `name`, fail."""
    spec = PatchSpec(
        target="submission.x",
        kind="source",
        source="x = 7\n",  # no callable named `wrong_name`
        name="wrong_name",
    )
    with pytest.raises(ValueError, match="did not define a callable"):
        _build_mock_from_spec(spec)


# ---- End-to-end through run_request -------------------------------------


def test_run_request_applies_noop_patch_during_call(submission_dir):
    """A `noop` patch_spec replaces the target inside the worker."""
    _write(
        submission_dir,
        "submission.py",
        """
        import os
        def main():
            # If the patch worked, this call is a noop and we return 1.
            # If it didn't, calling exit() would terminate the process.
            exit(99)
            return 1
        """,
    )
    spec = PatchSpec(target="builtins.exit", kind="noop")
    resp = run_request(_request(submission_dir, patch_specs=(spec,)))
    assert resp.exception is None
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == 1


def test_run_request_applies_iter_returns_patch(submission_dir):
    """A patched submission.greet returns successive values from the spec."""
    _write(
        submission_dir,
        "submission.py",
        """
        def greet():
            return "real"
        def main():
            return [greet(), greet()]
        """,
    )
    spec = PatchSpec(
        target="submission.greet", kind="iter_returns", values=["hi", "bye"]
    )
    resp = run_request(_request(submission_dir, patch_specs=(spec,)))
    assert resp.exception is None
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == ["hi", "bye"]


def test_run_request_applies_raise_error_patch(submission_dir):
    """A `raise_error` patch raises the resolved class on call."""
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            exit(0)
        """,
    )
    spec = PatchSpec(
        target="builtins.exit",
        kind="raise_error",
        error_qualname="generic_grader.utils.exceptions.ExitError",
    )
    resp = run_request(_request(submission_dir, patch_specs=(spec,)))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "ExitError"


def test_run_request_applies_source_patch(submission_dir):
    """A `source` patch defines a callable that replaces the target."""
    _write(
        submission_dir,
        "submission.py",
        """
        def falling_dist(t):
            # Real implementation would compute physics; we expect the
            # patched fake to be called instead.
            raise RuntimeError("real falling_dist should not run")

        def main():
            return [falling_dist(0), falling_dist(2)]
        """,
    )
    src = textwrap.dedent(
        """
        def fake_falling_dist(time):
            return (time * 1234567.89) % 125
        """
    )
    spec = PatchSpec(
        target="submission.falling_dist",
        kind="source",
        source=src,
        name="fake_falling_dist",
    )
    resp = run_request(_request(submission_dir, patch_specs=(spec,)))
    assert resp.exception is None
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == [0.0, (2 * 1234567.89) % 125]


def test_run_request_patches_active_during_module_import(submission_dir):
    """Module-top-level code observing the patched target sees the mock.

    This catches the bug where patches were applied only around the
    call (so module-level invocations of the target would see the
    real attribute).
    """
    _write(
        submission_dir,
        "submission.py",
        """
        # Top-level call captures the patched value at import time.
        TOP_LEVEL = exit  # bound reference at module load
        def main():
            return TOP_LEVEL.__name__
        """,
    )
    # Replace `builtins.exit` with a noop so the top-level binding
    # picks up the patched function.
    spec = PatchSpec(target="builtins.exit", kind="noop")
    resp = run_request(_request(submission_dir, patch_specs=(spec,)))
    assert resp.exception is None
    returns = [e for e in resp.events if e.type == "return"]
    # The patched noop is a locally-defined function named `_noop`.
    assert returns[0].value == "_noop"


def test_run_request_reports_patch_target_validation_error(submission_dir):
    """A malformed patch target surfaces as a structured exception."""
    _write(submission_dir, "submission.py", "def main(): return 1\n")
    # ``target`` has no dot, so it can't be a dotted patch path.
    spec = PatchSpec(target="invalidtarget", kind="noop")
    resp = run_request(_request(submission_dir, patch_specs=(spec,)))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "ValueError"
    assert "Invalid patch target" in resp.exception[0]["message"]


def test_enter_patches_from_specs_with_empty_tuple_is_noop():
    """No specs => stack unchanged; no exceptions."""
    from contextlib import ExitStack

    with ExitStack() as stack:
        _enter_patches_from_specs(stack, ())


def test_run_request_reverts_patches_after_call(submission_dir):
    """Patches applied for one request don't leak into the next."""
    import builtins as _b

    original_exit = _b.exit
    _write(submission_dir, "submission.py", "def main(): return 1\n")
    spec = PatchSpec(target="builtins.exit", kind="noop")
    run_request(_request(submission_dir, patch_specs=(spec,)))
    # After the request completes, builtins.exit is restored.
    assert _b.exit is original_exit


# ---------------------------------------------------------------------------
# Student-call SIGALRM time limit
# ---------------------------------------------------------------------------


def test_run_request_enforces_student_call_time_limit_via_sigalrm(submission_dir):
    """A student call that overruns ``time_limit_seconds`` raises
    ``UserTimeoutError`` (legacy ``Options.time_limit`` semantics).

    The alarm wraps only the call -- not interpreter startup, not
    import.  We give a short student-code budget and a deliberately
    slow ``main`` to force the alarm to fire deterministically.
    """
    _write(
        submission_dir,
        "submission.py",
        """
        import time

        def main():
            time.sleep(3)
        """,
    )
    resp = run_request(_request(submission_dir, time_limit_seconds=0.05))
    assert resp.exception is not None, "expected the alarm to fire"
    head = resp.exception[0]
    assert head["type"] == "UserTimeoutError"


def test_run_request_disables_alarm_when_time_limit_non_positive(submission_dir):
    """A non-positive ``time_limit_seconds`` disables the alarm.

    This keeps the worker safe in pathological configurations and
    documents the behavior of ``_student_call_time_limit(seconds<=0)``,
    which is exercised by the early-return branch in the context
    manager.
    """
    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return "ok"
        """,
    )
    # A 0-second budget would kill *any* student code if the alarm
    # were armed; we expect the disabled-alarm branch to let this run.
    resp = run_request(_request(submission_dir, time_limit_seconds=0))
    assert resp.exception is None


def test_run_request_pluralizes_timeout_message_when_budget_is_one_second(
    submission_dir,
):
    """``UserTimeoutError`` message says "1 second" (singular) when the
    budget is exactly one second, matching the legacy non-sandbox
    ``resource_limits.time_limit`` wording.
    """
    _write(
        submission_dir,
        "submission.py",
        """
        import time

        def main():
            time.sleep(3)
        """,
    )
    resp = run_request(_request(submission_dir, time_limit_seconds=1))
    assert resp.exception is not None
    head = resp.exception[0]
    assert head["type"] == "UserTimeoutError"
    # The legacy phrasing is "1 second." (singular); anything else
    # gets the plural form.
    assert "1 second." in head["message"]


def test_run_request_cancels_pending_alarm_when_call_returns_quickly(
    submission_dir,
):
    """The alarm is cancelled on the way out of the call, even when
    the student code returns well before the budget expires.

    Without the cancellation in ``_student_call_time_limit``'s
    ``finally`` block, a leftover ``setitimer`` could fire later (for
    example during figure serialization) and turn a clean run into a
    spurious ``UserTimeoutError``.
    """
    import signal as _signal

    _write(
        submission_dir,
        "submission.py",
        """
        def main():
            return 1
        """,
    )
    resp = run_request(_request(submission_dir, time_limit_seconds=5.0))
    assert resp.exception is None
    # The timer should be disarmed once the request returns.
    remaining, interval = _signal.getitimer(_signal.ITIMER_REAL)
    assert remaining == 0.0
    assert interval == 0.0
