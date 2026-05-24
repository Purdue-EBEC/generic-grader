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
    """Running out of entries should surface as an EOFError in the chain."""
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
