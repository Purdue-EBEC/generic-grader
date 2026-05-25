"""Host-side runner that drives a sandboxed worker via ``isolate``.

The grader process (the host) calls `IsolateRunner.run(request)` for
each test.  The runner:

1. Allocates a free box via ``isolate --box-id N --init`` (and
   ``--cleanup`` after).
2. Builds the ``--run`` invocation with bind mounts, resource limits,
   and a meta file for post-mortem classification.
3. Spawns the child, writes the request frame to its stdin, reads
   the response frame from its stdout.
4. Parses the meta file to classify any abnormal exit (timeout,
   memory, signal, runtime error) and folds it back into the
   `Response.exception` so callers always get a uniform structure.

The class is split into two layers:

* `build_run_argv()` is a pure function that returns the argv list
  for the ``--run`` invocation.  It is the part that holds all the
  isolate CLI knowledge and so it gets the densest unit-test coverage.
* `IsolateRunner.run()` orchestrates init / spawn / parse / cleanup
  with everything that *isn't* command construction.  It accepts an
  injectable ``subprocess_runner`` so the unit tests can stub real
  ``isolate`` calls without needing the privileged binary installed.

This makes the runner exercisable in CI environments that don't have
``isolate`` while still letting us run an integration test against a
real install when one is available.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Sequence

from generic_grader.sandbox.protocol import (
    Request,
    Response,
    SandboxException,
    read_response,
    write_request,
)

DEFAULT_BOX_ID = 0
DEFAULT_WALL_TIME_MULTIPLIER = 2.0
DEFAULT_PROCESSES = 64
DEFAULT_FSIZE_KB = 65536  # 64 MB of file writes per test


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


@dataclass
class RunPlan:
    """A fully-resolved description of one isolate run.

    Construction is pure: no filesystem mutation, no subprocess calls.
    Tests build a `RunPlan` and assert on its argv.
    """

    box_id: int
    submission_dir: str
    grader_src: str
    python_executable: str
    meta_path: str
    time_limit_seconds: float
    wall_time_limit_seconds: float
    memory_limit_mb: int
    processes: int
    fsize_kb: int
    extra_dirs: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    isolate_binary: str = "isolate"

    def init_argv(self) -> list[str]:
        return [self.isolate_binary, "--box-id", str(self.box_id), "--init"]

    def cleanup_argv(self) -> list[str]:
        return [self.isolate_binary, "--box-id", str(self.box_id), "--cleanup"]

    def run_argv(self) -> list[str]:
        argv: list[str] = [
            self.isolate_binary,
            "--box-id",
            str(self.box_id),
            "--meta",
            self.meta_path,
            "--time",
            f"{self.time_limit_seconds:.3f}",
            "--wall-time",
            f"{self.wall_time_limit_seconds:.3f}",
            "--mem",
            str(self.memory_limit_mb * 1024),  # isolate expects KB
            "--processes",
            str(self.processes),
            "--fsize",
            str(self.fsize_kb),
            # /box/submission is the worker's CWD and is writable.
            "--dir",
            f"/box/submission={self.submission_dir}:rw",
            # /box/grader is the generic_grader install, read only.
            "--dir",
            f"/box/grader={self.grader_src}",
            # Set PYTHONPATH and a sane cwd.
            "--env",
            "PYTHONPATH=/box/grader",
            "--env",
            "MPLBACKEND=Agg",
            "--env",
            "HOME=/box/submission",
            "--chdir",
            "/box/submission",
            # Default isolate already disables network; pass --share-net
            # is what enables it, so we deliberately omit that flag.
        ]
        for name, source, opts in self.extra_dirs:
            spec = f"/box/{name}={source}"
            if opts:
                spec = f"{spec}:{opts}"
            argv.extend(["--dir", spec])
        argv.extend(
            [
                "--run",
                "--",
                self.python_executable,
                "-I",
                "-S",
                "-m",
                "generic_grader.sandbox.worker_main",
            ]
        )
        return argv


def build_run_plan(
    request: Request,
    *,
    box_id: int,
    grader_src: str,
    meta_path: str,
    python_executable: str | None = None,
    isolate_binary: str = "isolate",
    extra_dirs: Sequence[tuple[str, str, str]] = (),
) -> RunPlan:
    """Construct a :class:`RunPlan` from a :class:`Request`.

    Resource limits come straight from the request -- `Request`
    already supplies sensible defaults (1s, 1400 MB) so the runner
    doesn't need to layer its own.  Tests that need a different
    limit override it on the request.
    """
    time_limit = request.time_limit_seconds
    wall_limit = time_limit * DEFAULT_WALL_TIME_MULTIPLIER
    mem_mb = request.memory_limit_mb
    python_exe = python_executable or sys.executable
    return RunPlan(
        box_id=box_id,
        submission_dir=request.submission_dir,
        grader_src=grader_src,
        python_executable=python_exe,
        meta_path=meta_path,
        time_limit_seconds=time_limit,
        wall_time_limit_seconds=wall_limit,
        memory_limit_mb=mem_mb,
        processes=DEFAULT_PROCESSES,
        fsize_kb=DEFAULT_FSIZE_KB,
        extra_dirs=tuple(extra_dirs),
        isolate_binary=isolate_binary,
    )


# ---------------------------------------------------------------------------
# Meta-file parsing
# ---------------------------------------------------------------------------


def parse_meta(meta_text: str) -> dict[str, str]:
    """Parse the `key:value` lines isolate writes to its meta file."""
    out: dict[str, str] = {}
    for raw in meta_text.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def classify_meta(meta: dict[str, str]) -> dict[str, str] | None:
    """Map isolate's meta file to a structured exception entry.

    Returns ``None`` when the run looks clean (no status code, exit
    code 0), otherwise a dict matching the exception-chain shape used
    elsewhere in the protocol.
    """
    status = meta.get("status")
    if status:
        if status == "TO":
            return {
                "type": "SandboxTimeout",
                "message": meta.get("message", "Wall-time or CPU-time limit exceeded."),
                "traceback": "",
            }
        if status == "ML":
            return {
                "type": "SandboxMemoryLimit",
                "message": meta.get("message", "Memory limit exceeded."),
                "traceback": "",
            }
        if status == "SG":
            return {
                "type": "SandboxSignal",
                "message": meta.get(
                    "message", f"Killed by signal {meta.get('exitsig', '?')}."
                ),
                "traceback": "",
            }
        if status == "XX":
            return {
                "type": "SandboxInternalError",
                "message": meta.get("message", "Sandbox internal error."),
                "traceback": "",
            }
        # Anything else (e.g. "RE" runtime error) is the worker exiting
        # nonzero -- the worker itself reports its exception in the
        # response payload, so we only synthesize one here if the
        # exit code is set and nonzero. The caller decides what to
        # do based on whether a response frame was read.
        return {
            "type": "SandboxAbnormalExit",
            "message": meta.get(
                "message",
                f"Worker exited with status={status} exitcode={meta.get('exitcode', '?')}.",
            ),
            "traceback": "",
        }
    exitcode = meta.get("exitcode", "0")
    if exitcode and exitcode != "0":
        return {
            "type": "SandboxAbnormalExit",
            "message": f"Worker exited with exitcode={exitcode}.",
            "traceback": "",
        }
    return None


# ---------------------------------------------------------------------------
# Subprocess hook
# ---------------------------------------------------------------------------


SubprocessRunner = Callable[..., subprocess.CompletedProcess]


def _default_subprocess_runner(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(*args, **kwargs)


# Hard cap on the worker's stdout the runner is willing to buffer.
# ``subprocess.run(capture_output=True)`` reads the child's pipe into
# memory; without a cap a runaway worker that emits unbounded data
# (e.g. a flapping serializer in a tight loop) could OOM the host.
# 64 MiB is far larger than any realistic protocol frame (events are
# already capped indirectly by isolate's --fsize/wall-time limits)
# while still being a hard ceiling.
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class IsolateRunner:
    """High-level runner that drives a single sandboxed worker call."""

    grader_src: str
    isolate_binary: str = "isolate"
    box_id: int = DEFAULT_BOX_ID
    python_executable: str | None = None
    subprocess_runner: SubprocessRunner = _default_subprocess_runner
    extra_dirs: Sequence[tuple[str, str, str]] = ()
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, request: Request) -> Response:
        """Run `request` through a fresh sandboxed worker and return its `Response`."""
        if not shutil.which(self.isolate_binary):
            raise SandboxException(
                f"isolate binary not found at {self.isolate_binary!r}. "
                "Install isolate (e.g. `apt install isolate`) and run "
                "`sudo isolate --init` once before grading."
            )

        meta_fd, meta_path = tempfile.mkstemp(prefix="isolate-meta-", suffix=".txt")
        os.close(meta_fd)
        try:
            plan = build_run_plan(
                request,
                box_id=self.box_id,
                grader_src=self.grader_src,
                meta_path=meta_path,
                python_executable=self.python_executable,
                isolate_binary=self.isolate_binary,
                extra_dirs=self.extra_dirs,
            )

            init = self.subprocess_runner(
                plan.init_argv(),
                capture_output=True,
                text=True,
                check=False,
            )
            if init.returncode != 0:
                raise SandboxException(
                    f"`isolate --init` failed for box_id={self.box_id}: "
                    f"{init.stderr.strip() or init.stdout.strip()}"
                )

            try:
                stdin_bytes = _encode_request(request)
                completed = self.subprocess_runner(
                    plan.run_argv(),
                    input=stdin_bytes,
                    capture_output=True,
                    check=False,
                )
                stdout_bytes = completed.stdout or b""
                if len(stdout_bytes) > self.max_response_bytes:
                    raise SandboxException(
                        f"Worker stdout exceeded the {self.max_response_bytes}-byte "
                        f"cap ({len(stdout_bytes)} bytes received). This typically "
                        "indicates a malformed worker that wrote outside the "
                        "framed protocol; check the worker's stderr for clues."
                    )
                response = _decode_response_or_raise(
                    stdout_bytes,
                    completed.stderr,
                    completed.returncode,
                    meta_path,
                )
            finally:
                self.subprocess_runner(
                    plan.cleanup_argv(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
        finally:
            try:
                os.unlink(meta_path)
            except OSError:  # pragma: no cover - best effort
                pass

        return response


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _encode_request(request: Request) -> bytes:
    """Serialize a request to the framed wire format as bytes."""
    buf = io.BytesIO()
    write_request(buf, request)
    return buf.getvalue()


def _decode_response_or_raise(
    stdout_bytes: bytes,
    stderr_bytes: bytes,
    exit_code: int,
    meta_path: str,
) -> Response:
    """Decode the worker's response or synthesize one from the meta file.

    The runner has three kinds of outcomes:

    1. The worker wrote a complete frame -> decode and return it.
       If the meta file shows a sandbox-level abnormal exit (e.g. the
       runner killed the worker after it finished its frame), we
       still trust the worker's frame -- the host can layer additional
       diagnostics on top via the meta info if it wants.

    2. The worker wrote nothing (or a partial frame) -> the sandbox
       killed it before it could respond.  We synthesize a `Response`
       carrying the classified meta exception.

    3. The worker exited nonzero with no frame and no meta diagnostic
       -> last-resort generic failure with stderr included so the
       student can see Python's complaint about a missing module
       etc.
    """
    meta_text = ""
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta_text = f.read()
    except OSError:
        meta_text = ""
    meta = parse_meta(meta_text)
    classified = classify_meta(meta)

    if stdout_bytes:
        try:
            return read_response(io.BytesIO(stdout_bytes))
        except SandboxException:
            # Partial frame or junk: fall through to the synthetic path.
            pass

    # No frame -- build one from the meta classification.
    if classified is None:
        # No meta classification either; build a generic failure that
        # includes whatever the worker wrote to stderr.
        stderr_text = _decode_text(stderr_bytes)
        classified = {
            "type": "SandboxAbnormalExit",
            "message": (
                f"Worker exited with code {exit_code} and no response frame. "
                + (f"stderr: {stderr_text}" if stderr_text else "")
            ).strip(),
            "traceback": "",
        }

    return Response(
        events=[],
        exception=[classified],
        elapsed_seconds=_meta_time(meta),
    )


def _decode_text(buf: bytes) -> str:
    try:
        return buf.decode("utf-8", errors="replace").strip()
    except Exception:  # pragma: no cover - utf-8 with errors='replace' can't raise
        return ""


def _meta_time(meta: dict[str, str]) -> float:
    """Best-effort elapsed time from isolate's meta file (wall-time or time)."""
    for key in ("time-wall", "time"):
        if key in meta:
            try:
                return float(meta[key])
            except (TypeError, ValueError):
                continue
    return 0.0


__all__ = (
    "DEFAULT_BOX_ID",
    "IsolateRunner",
    "RunPlan",
    "build_run_plan",
    "classify_meta",
    "parse_meta",
)
