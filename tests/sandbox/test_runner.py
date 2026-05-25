"""Tests for the isolate-based sandbox runner.

The runner is split so the bulk of the logic is testable without a
real `isolate` install:

* `build_run_plan` / `RunPlan` are pure: tests assert directly on the
  argv they produce.
* `parse_meta` / `classify_meta` are pure string -> dict functions
  that we exercise with synthetic meta-file contents.
* `IsolateRunner.run` takes an injectable `subprocess_runner` so we
  can swap a real subprocess for a deterministic fake.

A separate integration test (skipped when `isolate` is unavailable)
exercises the real binary; see the bottom of the file.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from generic_grader.sandbox.protocol import (
    Event,
    Request,
    Response,
    SandboxException,
    write_response,
)
from generic_grader.sandbox.runner import (
    IsolateRunner,
    build_run_plan,
    classify_meta,
    parse_meta,
)

# ---------------------------------------------------------------------------
# Pure-function tests: command construction
# ---------------------------------------------------------------------------


def _request(submission_dir: str, **overrides: Any) -> Request:
    base = dict(
        runtime="python",
        submission_dir=submission_dir,
        module="submission",
        obj_name="main",
    )
    base.update(overrides)
    return Request(**base)


def test_build_run_plan_uses_request_resource_limits(tmp_path):
    req = _request(
        str(tmp_path),
        time_limit_seconds=5.0,
        memory_limit_mb=128,
    )
    plan = build_run_plan(
        req,
        box_id=3,
        grader_src="/grader/src",
        meta_path="/tmp/meta.txt",
        python_executable="/usr/bin/python3",
    )
    assert plan.box_id == 3
    assert plan.submission_dir == str(tmp_path)
    assert plan.time_limit_seconds == 5.0
    assert plan.memory_limit_mb == 128


def test_build_run_plan_uses_request_defaults_when_limits_unspecified(tmp_path):
    """Request itself supplies defaults; the plan reflects them verbatim."""
    req = _request(str(tmp_path))
    plan = build_run_plan(
        req,
        box_id=0,
        grader_src="/grader/src",
        meta_path="/tmp/meta.txt",
    )
    # Request default is 1.0s / 1400 MB
    assert plan.time_limit_seconds == 1.0
    assert plan.memory_limit_mb == 1400
    # Wall-time is double the CPU time.
    assert plan.wall_time_limit_seconds == 2.0


def test_build_run_plan_uses_sys_executable_when_python_executable_unset(tmp_path):
    import sys

    req = _request(str(tmp_path))
    plan = build_run_plan(
        req,
        box_id=0,
        grader_src="/grader/src",
        meta_path="/tmp/meta.txt",
    )
    assert plan.python_executable == sys.executable


def test_init_argv_uses_box_id_and_isolate_binary(tmp_path):
    plan = build_run_plan(
        _request(str(tmp_path)),
        box_id=7,
        grader_src="/grader/src",
        meta_path="/tmp/meta.txt",
        isolate_binary="/usr/bin/isolate",
    )
    assert plan.init_argv() == ["/usr/bin/isolate", "--box-id", "7", "--init"]
    assert plan.cleanup_argv() == ["/usr/bin/isolate", "--box-id", "7", "--cleanup"]


def test_run_argv_carries_resource_limits(tmp_path):
    req = _request(
        str(tmp_path),
        time_limit_seconds=4.0,
        memory_limit_mb=64,
    )
    plan = build_run_plan(
        req,
        box_id=0,
        grader_src="/grader/src",
        meta_path="/tmp/meta.txt",
    )
    argv = plan.run_argv()
    assert "--time" in argv
    assert argv[argv.index("--time") + 1] == "4.000"
    assert "--wall-time" in argv
    # memory is in KB inside the argv
    assert "--mem" in argv
    assert argv[argv.index("--mem") + 1] == str(64 * 1024)


def test_run_argv_includes_required_bind_mounts(tmp_path):
    req = _request(str(tmp_path))
    plan = build_run_plan(
        req,
        box_id=0,
        grader_src="/path/to/grader",
        meta_path="/tmp/meta.txt",
    )
    argv = plan.run_argv()
    # /box/submission is RW and points at the request's submission_dir
    assert f"/box/submission={tmp_path}:rw" in argv
    # /box/grader is RO and points at the grader source
    assert "/box/grader=/path/to/grader" in argv


def test_run_argv_sets_environment(tmp_path):
    req = _request(str(tmp_path))
    plan = build_run_plan(
        req,
        box_id=0,
        grader_src="/path/to/grader",
        meta_path="/tmp/meta.txt",
    )
    argv = plan.run_argv()
    assert "PYTHONPATH=/box/grader" in argv
    assert "MPLBACKEND=Agg" in argv
    assert "HOME=/box/submission" in argv


def test_run_argv_does_not_enable_network(tmp_path):
    """The runner relies on isolate's default of network isolation."""
    plan = build_run_plan(
        _request(str(tmp_path)),
        box_id=0,
        grader_src="/g",
        meta_path="/tmp/meta.txt",
    )
    assert "--share-net" not in plan.run_argv()


def test_run_argv_appends_extra_dirs(tmp_path):
    plan = build_run_plan(
        _request(str(tmp_path)),
        box_id=0,
        grader_src="/g",
        meta_path="/tmp/meta.txt",
        extra_dirs=[("etc", "/etc", ""), ("opt", "/opt/cache", "rw")],
    )
    argv = plan.run_argv()
    assert "/box/etc=/etc" in argv
    assert "/box/opt=/opt/cache:rw" in argv


def test_run_argv_runs_worker_main_module(tmp_path):
    """Argv ends with `-m generic_grader.sandbox.worker_main`."""
    plan = build_run_plan(
        _request(str(tmp_path)),
        box_id=0,
        grader_src="/g",
        meta_path="/tmp/meta.txt",
        python_executable="/usr/bin/python3",
    )
    argv = plan.run_argv()
    assert "--run" in argv
    assert "--" in argv
    tail = argv[argv.index("--") + 1 :]
    assert tail[0] == "/usr/bin/python3"
    assert tail[-1] == "generic_grader.sandbox.worker_main"
    assert "-m" in tail


# ---------------------------------------------------------------------------
# Pure-function tests: meta parsing & classification
# ---------------------------------------------------------------------------


def test_parse_meta_extracts_known_keys():
    meta = parse_meta("time:1.234\nstatus:TO\nmessage:Timed out\n")
    assert meta == {"time": "1.234", "status": "TO", "message": "Timed out"}


def test_parse_meta_ignores_blank_and_malformed_lines():
    meta = parse_meta("time:1.0\n\n\nthisisnotvalid\nexitcode:0\n")
    assert meta == {"time": "1.0", "exitcode": "0"}


def test_classify_meta_clean_run_returns_none():
    assert classify_meta({"time": "0.1", "exitcode": "0"}) is None


def test_classify_meta_clean_run_with_no_keys_returns_none():
    assert classify_meta({}) is None


def test_classify_meta_timeout_maps_to_sandbox_timeout():
    out = classify_meta({"status": "TO", "message": "limit"})
    assert out["type"] == "SandboxTimeout"
    assert "limit" in out["message"]


def test_classify_meta_memory_limit_maps_to_sandbox_memory_limit():
    out = classify_meta({"status": "ML"})
    assert out["type"] == "SandboxMemoryLimit"


def test_classify_meta_signal_maps_to_sandbox_signal():
    out = classify_meta({"status": "SG", "exitsig": "9"})
    assert out["type"] == "SandboxSignal"
    assert "9" in out["message"]


def test_classify_meta_internal_error_maps_to_sandbox_internal_error():
    out = classify_meta({"status": "XX", "message": "boom"})
    assert out["type"] == "SandboxInternalError"
    assert "boom" in out["message"]


def test_classify_meta_unknown_status_maps_to_abnormal_exit():
    out = classify_meta({"status": "RE", "exitcode": "1"})
    assert out["type"] == "SandboxAbnormalExit"


def test_classify_meta_no_status_but_nonzero_exitcode_maps_to_abnormal_exit():
    out = classify_meta({"exitcode": "2"})
    assert out["type"] == "SandboxAbnormalExit"


# ---------------------------------------------------------------------------
# IsolateRunner.run() with injected subprocess
# ---------------------------------------------------------------------------


class FakeIsolate:
    """A stand-in for the isolate binary that records calls and returns canned data.

    Wired into `IsolateRunner` via `subprocess_runner=`. Each call
    appends a (argv, stdin_bytes) tuple to `calls` and dispatches
    based on the subcommand at argv position 3 (init / cleanup / run).
    """

    def __init__(
        self,
        *,
        run_stdout: bytes = b"",
        run_stderr: bytes = b"",
        run_returncode: int = 0,
        meta_text: str = "time:0.05\nexitcode:0\n",
        init_returncode: int = 0,
        init_stderr: str = "",
    ) -> None:
        self.run_stdout = run_stdout
        self.run_stderr = run_stderr
        self.run_returncode = run_returncode
        self.meta_text = meta_text
        self.init_returncode = init_returncode
        self.init_stderr = init_stderr
        self.calls: list[tuple[list[str], bytes | None]] = []

    def __call__(self, argv, **kwargs):
        # Always record the call for assertions.
        self.calls.append((list(argv), kwargs.get("input")))

        if "--init" in argv:
            return subprocess.CompletedProcess(
                argv, self.init_returncode, "", self.init_stderr
            )
        if "--cleanup" in argv:
            return subprocess.CompletedProcess(argv, 0, "", "")
        # --run path: write meta to the path given by --meta and return
        # the canned stdout/stderr.
        meta_path = argv[argv.index("--meta") + 1]
        Path(meta_path).write_text(self.meta_text)
        return subprocess.CompletedProcess(
            argv,
            self.run_returncode,
            self.run_stdout,
            self.run_stderr,
        )


def _make_runner(
    fake: FakeIsolate, *, isolate_binary: str = "/fake/isolate"
) -> IsolateRunner:
    return IsolateRunner(
        grader_src="/grader/src",
        isolate_binary=isolate_binary,
        box_id=0,
        subprocess_runner=fake,
    )


def _make_response_bytes(
    events: tuple[Event, ...] = (),
    exception=None,
    elapsed: float = 0.5,
) -> bytes:
    buf = io.BytesIO()
    write_response(
        buf,
        Response(events=list(events), exception=exception, elapsed_seconds=elapsed),
    )
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _patch_which(monkeypatch: pytest.MonkeyPatch):
    """Make `shutil.which` claim the fake isolate is on PATH."""
    monkeypatch.setattr(
        "generic_grader.sandbox.runner.shutil.which",
        lambda cmd: cmd if cmd == "/fake/isolate" else None,
    )


def test_runner_invokes_init_run_cleanup_in_order(tmp_path):
    """Each run goes through init -> run -> cleanup."""
    fake = FakeIsolate(
        run_stdout=_make_response_bytes(events=(Event(type="return", value=42),)),
    )
    runner = _make_runner(fake)
    runner.run(_request(str(tmp_path)))
    subcommands = []
    for argv, _stdin in fake.calls:
        for flag in ("--init", "--run", "--cleanup"):
            if flag in argv:
                subcommands.append(flag)
    assert subcommands == ["--init", "--run", "--cleanup"]


def test_runner_writes_request_frame_to_worker_stdin(tmp_path):
    fake = FakeIsolate(
        run_stdout=_make_response_bytes(events=(Event(type="return", value=1),)),
    )
    runner = _make_runner(fake)
    runner.run(_request(str(tmp_path)))
    run_calls = [c for c in fake.calls if "--run" in c[0]]
    assert len(run_calls) == 1
    stdin_bytes = run_calls[0][1]
    assert stdin_bytes is not None
    # Frame format: <decimal length>\n<json>
    newline_index = stdin_bytes.index(b"\n")
    length = int(stdin_bytes[:newline_index])
    payload = stdin_bytes[newline_index + 1 :]
    assert len(payload) == length


def test_runner_returns_decoded_response_when_worker_succeeds(tmp_path):
    fake = FakeIsolate(
        run_stdout=_make_response_bytes(
            events=(Event(type="return", value=7),),
            elapsed=0.123,
        ),
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == 7
    assert resp.exception is None


def test_runner_synthesizes_timeout_response_when_worker_killed(tmp_path):
    fake = FakeIsolate(
        run_stdout=b"",
        run_returncode=124,
        meta_text="status:TO\ntime:1.99\nmessage:Time limit exceeded\n",
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path), time_limit_seconds=1.0))
    assert resp.exception is not None
    assert resp.exception[0]["type"] == "SandboxTimeout"
    # The elapsed time should be picked up from the meta file.
    assert resp.elapsed_seconds == pytest.approx(1.99, rel=1e-3)


def test_runner_synthesizes_memory_response_when_worker_oom(tmp_path):
    fake = FakeIsolate(
        run_stdout=b"",
        run_returncode=137,
        meta_text="status:ML\ntime:0.10\n",
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    assert resp.exception[0]["type"] == "SandboxMemoryLimit"


def test_runner_synthesizes_generic_failure_when_no_meta_and_no_frame(tmp_path):
    fake = FakeIsolate(
        run_stdout=b"",
        run_stderr=b"ImportError: no module named 'foo'\n",
        run_returncode=1,
        meta_text="",
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    assert resp.exception[0]["type"] == "SandboxAbnormalExit"
    # The student-visible message should include stderr so the
    # underlying Python complaint is reachable.
    assert "ImportError" in resp.exception[0]["message"]


def test_runner_recovers_when_meta_file_unreadable(tmp_path, monkeypatch):
    fake = FakeIsolate(
        run_stdout=b"",
        run_returncode=1,
        meta_text="",  # the FakeIsolate writes an empty meta file
    )

    # Force the meta file open to raise so we exercise the OSError path.
    real_open = open

    def fake_open(path, *args, **kwargs):
        if "isolate-meta-" in str(path):
            raise OSError("permission denied")
        return real_open(path, *args, **kwargs)  # pragma: no cover

    monkeypatch.setattr("builtins.open", fake_open)
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    # The runner still produces a SandboxAbnormalExit response.
    assert resp.exception[0]["type"] == "SandboxAbnormalExit"


def test_runner_returns_worker_frame_even_when_meta_classifies_abnormal(tmp_path):
    """When both a frame and a non-zero meta exist, the frame wins.

    Rationale: the worker successfully reported its own result, so
    the meta-level diagnostics are redundant. (The frame may itself
    carry the relevant exception.)
    """
    payload = _make_response_bytes(events=(Event(type="return", value=1),))
    fake = FakeIsolate(
        run_stdout=payload,
        run_returncode=0,
        meta_text="status:RE\nexitcode:1\n",
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    returns = [e for e in resp.events if e.type == "return"]
    assert returns[0].value == 1


def test_runner_partial_frame_falls_back_to_meta_classification(tmp_path):
    fake = FakeIsolate(
        run_stdout=b"99\nNOT_REALLY_A_JSON_FRAME",
        run_returncode=1,
        meta_text="status:TO\ntime:0.5\n",
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    assert resp.exception[0]["type"] == "SandboxTimeout"


def test_runner_raises_when_isolate_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "generic_grader.sandbox.runner.shutil.which",
        lambda cmd: None,
    )
    runner = IsolateRunner(
        grader_src="/g",
        isolate_binary="not-installed",
        subprocess_runner=lambda *a, **k: pytest.fail("should not be called"),
    )
    with pytest.raises(SandboxException) as exc:
        runner.run(_request(str(tmp_path)))
    assert "isolate" in str(exc.value).lower()


def test_runner_raises_when_init_fails(tmp_path):
    fake = FakeIsolate(
        init_returncode=1,
        init_stderr="box 0 already in use",
    )
    runner = _make_runner(fake)
    with pytest.raises(SandboxException) as exc:
        runner.run(_request(str(tmp_path)))
    assert "box 0 already in use" in str(exc.value)


def test_runner_cleans_up_meta_file_after_run(tmp_path):
    """Meta files live in tempdir; the runner must delete them on the way out."""
    fake = FakeIsolate(
        run_stdout=_make_response_bytes(events=(Event(type="return", value=1),)),
    )
    runner = _make_runner(fake)

    # Snapshot meta files before; they live in the system tempdir with
    # a recognizable prefix.
    import tempfile

    tmp_root = Path(tempfile.gettempdir())
    before = set(tmp_root.glob("isolate-meta-*"))
    runner.run(_request(str(tmp_path)))
    after = set(tmp_root.glob("isolate-meta-*"))
    assert before == after


def test_runner_runs_cleanup_even_when_worker_failed(tmp_path):
    """Cleanup must happen on every run, even when --run returned nonzero."""
    fake = FakeIsolate(
        run_stdout=b"",
        run_returncode=1,
        meta_text="status:RE\nexitcode:1\n",
    )
    runner = _make_runner(fake)
    runner.run(_request(str(tmp_path)))
    cleanup_calls = [c for c in fake.calls if "--cleanup" in c[0]]
    assert len(cleanup_calls) == 1


# ---------------------------------------------------------------------------
# worker_main entry point
# ---------------------------------------------------------------------------


def test_worker_main_round_trips_request(tmp_path):
    """worker_main should consume a framed request and produce a framed response."""
    import textwrap

    from generic_grader.sandbox.protocol import read_response, write_request
    from generic_grader.sandbox.worker_main import main

    (tmp_path / "submission.py").write_text(
        textwrap.dedent(
            """
            def main():
                return "ok"
            """
        )
    )
    request = Request(
        runtime="python",
        submission_dir=str(tmp_path),
        module="submission",
        obj_name="main",
    )
    stdin = io.BytesIO()
    write_request(stdin, request)
    stdin.seek(0)
    stdout = io.BytesIO()
    code = main(stdin=stdin, stdout=stdout)
    assert code == 0
    stdout.seek(0)
    response = read_response(stdout)
    returns = [e for e in response.events if e.type == "return"]
    assert returns[0].value == "ok"


def test_worker_main_reports_malformed_request_frame():
    """A malformed input frame produces a SandboxProtocolError response."""
    from generic_grader.sandbox.protocol import read_response
    from generic_grader.sandbox.worker_main import main

    stdin = io.BytesIO(b"NOT_A_LENGTH_PREFIX")
    stdout = io.BytesIO()
    code = main(stdin=stdin, stdout=stdout)
    assert code == 2
    stdout.seek(0)
    response = read_response(stdout)
    assert response.exception is not None
    assert response.exception[0]["type"] == "SandboxProtocolError"


def test_worker_main_reports_clean_eof_as_protocol_error():
    """An EOF on stdin (no frame at all) must not crash the worker.

    Regression: previously `run_request(None)` raised `AttributeError`.
    Now the worker emits a structured `SandboxProtocolError` response.
    """
    from generic_grader.sandbox.protocol import read_response
    from generic_grader.sandbox.worker_main import main

    stdin = io.BytesIO(b"")
    stdout = io.BytesIO()
    code = main(stdin=stdin, stdout=stdout)
    assert code == 2
    stdout.seek(0)
    response = read_response(stdout)
    assert response.exception is not None
    assert response.exception[0]["type"] == "SandboxProtocolError"
    assert "no request" in response.exception[0]["message"].lower()


# ---------------------------------------------------------------------------
# Default subprocess runner & misc helpers
# ---------------------------------------------------------------------------


def test_default_subprocess_runner_runs_real_subprocess():
    """The default runner is just `subprocess.run`."""
    from generic_grader.sandbox.runner import _default_subprocess_runner

    out = _default_subprocess_runner(
        ["python", "-c", "print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0
    assert "ok" in out.stdout


def test_meta_time_returns_zero_when_values_unparseable(tmp_path):
    """Garbage in time / time-wall should not crash the runner."""
    fake = FakeIsolate(
        run_stdout=b"",
        run_returncode=1,
        meta_text="time:not-a-number\ntime-wall:also-bad\n",
    )
    runner = _make_runner(fake)
    resp = runner.run(_request(str(tmp_path)))
    assert resp.elapsed_seconds == 0.0


def test_run_rejects_worker_stdout_exceeding_cap(tmp_path):
    """A runaway worker that spews bytes is rejected, not buffered.

    Without a cap, `subprocess.run(capture_output=True)` would buffer
    the child's entire stdout into host memory.  The runner enforces
    a hard ceiling so an outsized payload becomes an actionable
    SandboxException instead of an OOM.
    """
    fake = FakeIsolate(
        run_stdout=b"x" * 1000,
        run_returncode=0,
        meta_text="",
    )
    runner = IsolateRunner(
        grader_src=str(tmp_path / "src"),
        isolate_binary="/fake/isolate",
        box_id=1,
        python_executable=sys.executable,
        subprocess_runner=fake,
        max_response_bytes=100,
    )
    with pytest.raises(SandboxException, match="exceeded"):
        runner.run(_request(str(tmp_path)))


# ---------------------------------------------------------------------------
# Optional real-isolate integration test
# ---------------------------------------------------------------------------


_ORIGINAL_SHUTIL_WHICH = shutil.which
REAL_ISOLATE = _ORIGINAL_SHUTIL_WHICH("isolate")


def _isolate_can_bind_mount() -> bool:  # pragma: no cover - env probe
    """Probe whether nested bind mounts are permitted in this environment.

    Containerized CI/dev environments often disallow the bind mounts that
    `isolate` relies on; in those environments the smoke test can't run
    even when the binary itself is installed.
    """
    if REAL_ISOLATE is None:
        return False
    probe = tempfile.mkdtemp(prefix="isolate-probe-")
    try:
        os.chmod(probe, 0o755)
        # Use a unique box id we don't expect anything else to be using.
        subprocess.run(
            [REAL_ISOLATE, "--box-id=99", "--cleanup"],
            capture_output=True,
            check=False,
        )
        init = subprocess.run(
            [REAL_ISOLATE, "--box-id=99", "--init"],
            capture_output=True,
            text=True,
            check=False,
        )
        if init.returncode != 0:
            return False
        try:
            result = subprocess.run(
                [
                    REAL_ISOLATE,
                    "--box-id=99",
                    f"--dir=/box/probe={probe}",
                    "--run",
                    "--",
                    "/bin/true",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        finally:
            subprocess.run(
                [REAL_ISOLATE, "--box-id=99", "--cleanup"],
                capture_output=True,
                check=False,
            )
    finally:
        shutil.rmtree(probe, ignore_errors=True)


_REAL_ISOLATE_USABLE = _isolate_can_bind_mount()


@pytest.mark.skipif(
    not _REAL_ISOLATE_USABLE,
    reason=(
        "The `isolate` binary isn't installed, or the kernel disallows the "
        "nested bind mounts isolate uses (common in nested containers)."
    ),
)
def test_real_isolate_smoke(
    monkeypatch: pytest.MonkeyPatch,
):  # pragma: no cover - environment-dependent
    """End-to-end run against the real isolate binary."""
    # Undo the autouse `_patch_which` fixture so the real binary is found.
    monkeypatch.setattr(
        "generic_grader.sandbox.runner.shutil.which", _ORIGINAL_SHUTIL_WHICH
    )
    # isolate's sandbox UID needs to traverse the submission and grader
    # paths, so use a world-traversable directory rather than the default
    # `tmp_path` (which lives under a 0700 `/tmp/pytest-of-<user>` tree).
    sub_dir = tempfile.mkdtemp(prefix="isolate-smoke-sub-")
    os.chmod(sub_dir, 0o755)
    try:
        (Path(sub_dir) / "submission.py").write_text("def main():\n    return 42\n")
        grader_src = Path(__file__).resolve().parents[2] / "src"
        runner = IsolateRunner(grader_src=str(grader_src), box_id=0)
        resp = runner.run(_request(sub_dir))
        assert resp.exception is None, resp.exception
        returns = [e for e in resp.events if e.type == "return"]
        assert returns and returns[0].value == 42
    finally:
        shutil.rmtree(sub_dir, ignore_errors=True)
