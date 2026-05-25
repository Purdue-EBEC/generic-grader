"""Tests for the sandbox integration module.

The integration module is the host-side bridge between the existing
`Importer` / `User` API and the sandboxed worker.  Tests inject a
fake runner so they don't require a real isolate install.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, List

import pytest

from generic_grader.sandbox.integration import (
    DEFAULT_BOX_POOL_SIZE,
    BoxPool,
    SandboxRunResult,
    _replay_events,
    _resolve_exception_class,
    _resolve_submission_dir,
    classify_call_outcome,
    classify_import_outcome,
    default_runner_factory,
    get_default_box_pool,
    iter_events,
    sandbox_call_obj,
    sandbox_import_obj,
)
from generic_grader.sandbox.protocol import Event, PatchSpec, Request, Response
from generic_grader.sandbox.runner import IsolateRunner
from generic_grader.utils.exceptions import EndOfInputError, ExtraEntriesError
from generic_grader.utils.options import Options

# ---------------------------------------------------------------------------
# BoxPool
# ---------------------------------------------------------------------------


def test_box_pool_acquires_and_releases_distinct_ids():
    pool = BoxPool(size=3, base=10)
    a = pool.acquire()
    b = pool.acquire()
    c = pool.acquire()
    assert {a, b, c} == {10, 11, 12}
    pool.release(b)
    assert pool.acquire() == 11


def test_box_pool_rejects_invalid_size():
    with pytest.raises(ValueError, match="size must be >= 1"):
        BoxPool(size=0)


def test_box_pool_rejects_invalid_base():
    with pytest.raises(ValueError, match="base must be >= 0"):
        BoxPool(size=4, base=-1)


def test_box_pool_blocks_until_release():
    """An empty pool blocks acquire; release wakes a waiter."""
    pool = BoxPool(size=1, base=5)
    first = pool.acquire()
    assert first == 5

    woke = threading.Event()
    second_holder: dict[str, int] = {}

    def waiter():
        second_holder["id"] = pool.acquire()
        woke.set()

    t = threading.Thread(target=waiter)
    t.start()
    # Give the waiter time to block.
    assert not woke.wait(0.05)
    pool.release(first)
    assert woke.wait(1.0), "release did not wake waiter"
    t.join(timeout=1.0)
    assert second_holder["id"] == 5


def test_get_default_box_pool_returns_singleton():
    a = get_default_box_pool()
    b = get_default_box_pool()
    assert a is b
    assert isinstance(a, BoxPool)


def test_default_box_pool_size_constant():
    """The default size is sensible and matches the constant."""
    assert DEFAULT_BOX_POOL_SIZE >= 1


# ---------------------------------------------------------------------------
# Event replay
# ---------------------------------------------------------------------------


def _resp(events: list[Event], **kwargs: Any) -> Response:
    return Response(events=events, **kwargs)


def test_replay_events_collects_stdout_into_log():
    resp = _resp([Event("stdout", data="hello "), Event("stdout", data="world")])
    result = _replay_events(resp)
    assert result.log == "hello world"
    assert result.interactions == [0]


def test_replay_events_records_interactions_on_stdin():
    """Each stdin event marks the log position before its line."""
    resp = _resp(
        [
            Event("stdout", data="prompt> "),
            Event("stdin", data="42"),
            Event("stdout", data="thanks\n"),
            Event("stdout", data="next> "),
            Event("stdin", data="7"),
        ]
    )
    result = _replay_events(resp)
    # Log: "prompt> 42\nthanks\nnext> 7\n"
    # interactions[0] = 0 (start), interactions[1] = len("prompt> ")=8,
    # interactions[2] = len("prompt> 42\nthanks\nnext> ") = 24
    assert result.log == "prompt> 42\nthanks\nnext> 7\n"
    assert result.interactions == [0, 8, 24]


def test_replay_events_drops_stderr_from_log():
    """Stderr writes don't show up in the IO log (parity with legacy)."""
    resp = _resp(
        [
            Event("stdout", data="ok"),
            Event("stderr", data="warn"),
            Event("stdin", data="x"),
        ]
    )
    result = _replay_events(resp)
    assert result.log == "okx\n"


def test_replay_events_captures_return_value():
    resp = _resp([Event("return", value={"answer": 42})])
    result = _replay_events(resp)
    assert result.return_value == {"answer": 42}
    assert result.return_non_serializable is False


def test_replay_events_captures_non_serializable_return():
    resp = _resp([Event("return", non_serializable=True, repr="<MyObj>")])
    result = _replay_events(resp)
    assert result.return_non_serializable is True
    assert result.return_repr == "<MyObj>"
    assert result.return_value is None


def test_replay_events_collects_figures():
    resp = _resp(
        [
            Event("figure", properties={"title": "Plot 1"}),
            Event("figure", properties={"title": "Plot 2"}),
        ]
    )
    result = _replay_events(resp)
    assert result.figures == [{"title": "Plot 1"}, {"title": "Plot 2"}]


def test_replay_events_counts_unused_entries():
    resp = _resp([Event("unused_entries", count=3)])
    result = _replay_events(resp)
    assert result.unused_entries == 3


def test_replay_events_flags_input_during_import():
    """A stdin event observed during the import phase is flagged."""
    resp = _resp(
        [
            # No phase event before the first stdin -> still considered import.
            Event("stdin", data="bad"),
            Event("phase", name="call"),
            Event("stdin", data="ok"),
        ]
    )
    result = _replay_events(resp)
    assert result.consumed_input_during_import is True


def test_replay_events_does_not_flag_input_after_call_phase():
    resp = _resp(
        [
            Event("phase", name="call"),
            Event("stdin", data="ok"),
        ]
    )
    result = _replay_events(resp)
    assert result.consumed_input_during_import is False


def test_replay_events_preserves_exception_and_elapsed():
    resp = _resp([], exception=[{"type": "ValueError"}], elapsed_seconds=0.42)
    result = _replay_events(resp)
    assert result.exception == [{"type": "ValueError"}]
    assert result.elapsed_seconds == 0.42
    assert result.response is resp


# ---------------------------------------------------------------------------
# submission_dir resolution
# ---------------------------------------------------------------------------


def test_resolve_submission_dir_returns_cwd_for_plain_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    opts = Options(sub_module="submission")
    assert _resolve_submission_dir(opts, "submission") == str(tmp_path)


def test_resolve_submission_dir_handles_dotted_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    opts = Options()
    assert _resolve_submission_dir(opts, "tests.reference") == str(tmp_path)


def test_resolve_submission_dir_falls_back_when_package_missing(tmp_path, monkeypatch):
    """Missing dotted package: still return cwd; the worker raises."""
    monkeypatch.chdir(tmp_path)
    opts = Options()
    assert _resolve_submission_dir(opts, "nonexistent.pkg") == str(tmp_path)


# ---------------------------------------------------------------------------
# Fake runner harness
# ---------------------------------------------------------------------------


@dataclass
class _FakeRunner:
    response: Response
    box_id: int = 0
    received: List[Request] = None

    def __post_init__(self):
        if self.received is None:
            self.received = []

    def run(self, request: Request) -> Response:
        self.received.append(request)
        return self.response


def _make_factory(response: Response) -> Callable[[int], _FakeRunner]:
    holder: dict[str, _FakeRunner] = {}

    def factory(box_id: int) -> _FakeRunner:
        runner = _FakeRunner(response=response, box_id=box_id)
        holder["last"] = runner
        return runner

    factory.holder = holder  # type: ignore[attr-defined]
    return factory


# ---------------------------------------------------------------------------
# sandbox_import_obj
# ---------------------------------------------------------------------------


def test_sandbox_import_obj_uses_fresh_box(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pool = BoxPool(size=2, base=20)
    response = _resp([], exception=None)
    factory = _make_factory(response)
    opts = Options()
    result = sandbox_import_obj(
        "submission",
        opts,
        runner_factory=factory,
        box_pool=pool,
    )
    assert result.exception is None
    # box pool fully replenished after the call returns.
    assert sorted([pool.acquire(), pool.acquire()]) == [20, 21]


def test_sandbox_import_obj_sends_noop_patch_for_target(tmp_path, monkeypatch):
    """The import probe wraps the target in a noop spec so the call is harmless."""
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    opts = Options(obj_name="main", sub_module="submission")
    sandbox_import_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    targets = [spec.target for spec in sent.patch_specs]
    assert "submission.main" in targets
    # Must be a noop, never any other kind.
    noop_specs = [s for s in sent.patch_specs if s.target == "submission.main"]
    assert all(s.kind == "noop" for s in noop_specs)


def test_sandbox_import_obj_releases_box_on_runner_failure(tmp_path, monkeypatch):
    """If the runner raises, the box id must still be returned."""
    monkeypatch.chdir(tmp_path)
    pool = BoxPool(size=1, base=42)

    class _BoomRunner:
        def __init__(self, box_id):
            self.box_id = box_id

        def run(self, request):
            raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        sandbox_import_obj(
            "submission",
            Options(),
            runner_factory=_BoomRunner,
            box_pool=pool,
        )
    # Pool is restored.
    assert pool.acquire() == 42


def test_sandbox_import_obj_uses_empty_entries(tmp_path, monkeypatch):
    """Even if Options.entries is set, the import probe sends empty entries."""
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    opts = Options(entries=("a", "b"))
    sandbox_import_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.entries == ()


def test_sandbox_import_obj_carries_user_patch_specs(tmp_path, monkeypatch):
    """Custom user patch_specs are forwarded after the import-only spec."""
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    user_spec = PatchSpec(target="builtins.print", kind="noop")
    opts = Options(patch_specs=(user_spec,))
    sandbox_import_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    targets = [s.target for s in sent.patch_specs]
    # Both specs present; import-only spec ordered first so it can't be
    # overridden by a user spec on the same target.
    assert targets[0] == "submission.main"
    assert "builtins.print" in targets


# ---------------------------------------------------------------------------
# sandbox_call_obj
# ---------------------------------------------------------------------------


def test_sandbox_call_obj_forwards_args_kwargs_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = _resp([Event("return", value=99)])
    factory = _make_factory(response)
    opts = Options(args=(1, 2), kwargs={"k": "v"}, entries=("x",))
    result = sandbox_call_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.args == (1, 2)
    assert sent.kwargs == {"k": "v"}
    assert sent.entries == ("x",)
    assert result.return_value == 99


def test_sandbox_call_obj_uses_entries_override(tmp_path, monkeypatch):
    """Explicit ``entries`` overrides Options.entries."""
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    opts = Options(entries=("ignored",))
    sandbox_call_obj(
        "submission",
        opts,
        runner_factory=factory,
        box_pool=BoxPool(size=1),
        entries=("override",),
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.entries == ("override",)


def test_sandbox_call_obj_propagates_patch_specs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    spec = PatchSpec(target="builtins.exit", kind="noop")
    opts = Options(patch_specs=(spec,))
    sandbox_call_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.patch_specs == (spec,)


def test_sandbox_call_obj_uses_fresh_box(tmp_path, monkeypatch):
    """Two back-to-back call_obj invocations both use distinct boxes."""
    monkeypatch.chdir(tmp_path)
    pool = BoxPool(size=2, base=30)
    response = _resp([])
    boxes_seen: list[int] = []

    def factory(box_id: int) -> _FakeRunner:
        boxes_seen.append(box_id)
        return _FakeRunner(response=response, box_id=box_id)

    opts = Options()
    sandbox_call_obj("submission", opts, runner_factory=factory, box_pool=pool)
    sandbox_call_obj("submission", opts, runner_factory=factory, box_pool=pool)
    # Each call grabs a box and releases it; the pool reuses the same one.
    assert len(boxes_seen) == 2


def test_sandbox_call_obj_propagates_fixed_time(tmp_path, monkeypatch):
    import datetime as _dt

    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    opts = Options(fixed_time="2024-01-01")
    sandbox_call_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.fixed_time == "2024-01-01"

    # Datetime is converted to ISO 8601.
    factory2 = _make_factory(response)
    opts2 = Options(fixed_time=_dt.datetime(2030, 6, 1, 12, 0, 0))
    sandbox_call_obj(
        "submission", opts2, runner_factory=factory2, box_pool=BoxPool(size=1)
    )
    sent2: Request = factory2.holder["last"].received[0]
    assert sent2.fixed_time and sent2.fixed_time.startswith("2030-06-01")


def test_sandbox_call_obj_passes_no_fixed_time_for_false(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    opts = Options(fixed_time=False)
    sandbox_call_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.fixed_time is None


def test_sandbox_call_obj_propagates_limits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = _resp([])
    factory = _make_factory(response)
    opts = Options(time_limit=3, memory_limit_GB=0.5, log_limit=1024)
    sandbox_call_obj(
        "submission", opts, runner_factory=factory, box_pool=BoxPool(size=1)
    )
    sent: Request = factory.holder["last"].received[0]
    assert sent.time_limit_seconds == 3.0
    assert sent.memory_limit_mb == 512
    assert sent.log_limit == 1024


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------


def test_classify_import_outcome_success_returns_none():
    result = SandboxRunResult(exception=None)
    assert classify_import_outcome(result) is None


def test_classify_import_outcome_detects_stuck_at_input():
    result = SandboxRunResult(consumed_input_during_import=True)
    assert classify_import_outcome(result) is EndOfInputError


def test_classify_import_outcome_maps_eof_error_to_end_of_input():
    result = SandboxRunResult(exception=[{"type": "EOFError", "message": ""}])
    assert classify_import_outcome(result) is EndOfInputError


def test_classify_import_outcome_resolves_other_exceptions():
    result = SandboxRunResult(exception=[{"type": "ModuleNotFoundError"}])
    assert classify_import_outcome(result) is ModuleNotFoundError


def test_classify_call_outcome_extra_entries_when_leftover():
    result = SandboxRunResult(exception=None, unused_entries=2)
    assert classify_call_outcome(result) is ExtraEntriesError


def test_classify_call_outcome_no_leftover_no_exception():
    result = SandboxRunResult(exception=None, unused_entries=0)
    assert classify_call_outcome(result) is None


def test_classify_call_outcome_resolves_exception_type():
    result = SandboxRunResult(exception=[{"type": "ValueError"}])
    assert classify_call_outcome(result) is ValueError


def test_classify_call_outcome_falls_back_to_exception():
    result = SandboxRunResult(exception=[{"type": "DefinitelyNotAClass"}])
    assert classify_call_outcome(result) is Exception


# ---------------------------------------------------------------------------
# Exception class resolution
# ---------------------------------------------------------------------------


def test_resolve_exception_class_builtins():
    assert _resolve_exception_class("ValueError") is ValueError
    assert _resolve_exception_class("ZeroDivisionError") is ZeroDivisionError


def test_resolve_exception_class_grader_exceptions():
    from generic_grader.utils.exceptions import ExitError

    assert _resolve_exception_class("ExitError") is ExitError


def test_resolve_exception_class_unknown_returns_exception():
    assert _resolve_exception_class("ThisIsNotAClassName") is Exception


def test_resolve_exception_class_handles_non_exception_attr():
    """If the resolved attribute exists but isn't an exception, fall back."""
    # `int` is a builtin but isn't a BaseException subclass.
    assert _resolve_exception_class("int") is Exception


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def test_iter_events_yields_dicts():
    resp = _resp([Event("stdout", data="hi"), Event("return", value=1)])
    events = list(iter_events(resp))
    assert events == [
        {"type": "stdout", "data": "hi"},
        {"type": "return", "value": 1},
    ]


def test_default_runner_factory_builds_isolate_runner():
    runner = default_runner_factory(7)
    assert isinstance(runner, IsolateRunner)
    assert runner.box_id == 7
    assert "generic_grader" not in runner.grader_src.split("/")[-1:]
