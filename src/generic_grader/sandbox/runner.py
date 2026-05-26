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
from dataclasses import dataclass, field, replace
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

# isolate bind-mounts the following host paths by default (see
# ``init_dir_rules`` in upstream ``rules.c``).  When the Python
# executable we want to run lives outside *all* of these roots --
# typical under ``uv``, ``pyenv``, ``conda``, or any venv outside
# ``/usr`` -- the chroot can't see it and ``execve`` fails with
# ``No such file or directory`` (exit 127).  In that case the
# runner has to add an extra ``--dir`` rule to expose the python
# prefix.
_ISOLATE_DEFAULT_MOUNT_ROOTS = ("/bin", "/dev", "/lib", "/lib64", "/proc", "/usr")

# The host-side submission directory is bind-mounted at this path
# inside the sandbox (see ``RunPlan.run_argv``).  The worker's CWD is
# also set to this path.  We rewrite ``Request.submission_dir`` to
# this value before serializing the frame, since the worker has no
# way to see the host path.
#
# Note that isolate's chroot root is the sandbox root, *not* ``/box``.
# By default isolate mounts the host ``<box_dir>/box`` directory at
# the sandbox path ``/box`` and chdirs there before running the
# program, but the default ``--dir`` mount points (``bin``, ``lib``,
# ``submission``, ...) all live at the sandbox root.  isolate refuses
# to create subdirectories in already-bound directories, so we cannot
# mount inside ``/box`` without pre-creating the mountpoint.  Mounting
# at the sandbox root is simpler and is what isolate does for every
# other tool that uses it (gitlab-ci, MOE Judge, OI judge, ...).
SANDBOX_SUBMISSION_DIR = "/submission"
SANDBOX_GRADER_DIR = "/grader"


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
            # ``--processes`` takes an *optional* argument per isolate's
            # getopt spec (``-p, --processes[=<max>]``), so the value
            # must be glued on with ``=``.  Passing them as separate
            # tokens makes isolate ignore the max and treat the count
            # as part of the command line, producing
            # ``execve("<N>"): No such file or directory``.
            f"--processes={self.processes}",
            "--fsize",
            str(self.fsize_kb),
            # ``isolate --dir`` target paths are relative to the
            # sandbox root (isolate strips a leading ``/`` from the
            # target).  We mount the host submission and grader at
            # ``/submission`` and ``/grader`` in the sandbox.  We do
            # *not* mount them under ``/box`` because isolate refuses
            # to create subdirectories in bound directories, and
            # ``/box`` is already a default bind-mount.
            "--dir",
            f"submission={self.submission_dir}:rw",
            # /grader is the generic_grader install, read only.
            "--dir",
            f"grader={self.grader_src}",
            # Set PYTHONPATH and a sane cwd.
            "--env",
            "PYTHONPATH=/grader",
            "--env",
            "MPLBACKEND=Agg",
            "--env",
            "HOME=/submission",
            # ``--chdir`` takes a path that, when ``chdir(2)``-ed from
            # the sandbox cwd (which is ``/box`` by default), lands at
            # the desired location.  Using ``/submission`` (absolute
            # under the chroot) is the most explicit form and works
            # regardless of any future change to the default cwd.
            "--chdir",
            "/submission",
            # Default isolate already disables network; pass --share-net
            # is what enables it, so we deliberately omit that flag.
        ]
        for name, source, opts in self.extra_dirs:
            # Mount targets must be relative to the box root; see the
            # comment on the ``submission`` mount above.
            spec = f"{name}={source}"
            if opts:
                spec = f"{spec}:{opts}"
            argv.extend(["--dir", spec])
        argv.extend(
            [
                "--run",
                "--",
                self.python_executable,
                # We *cannot* use ``-I`` (isolated mode) here because
                # it implies ``-E``, which makes Python ignore
                # ``PYTHONPATH`` -- and we rely on ``PYTHONPATH`` to
                # point at the bind-mounted grader install.  Instead
                # we pass the individual flags we want:
                #   ``-S`` -- do not run ``site.py`` on startup.
                #   ``-s`` -- do not add the per-user site directory.
                #   ``-P`` -- do not prepend the script's directory
                #             (or ``''`` for ``-m``) to ``sys.path``.
                #             Requires Python 3.11+, which is our
                #             minimum per ``pyproject.toml``.
                "-S",
                "-s",
                "-P",
                "-m",
                "generic_grader.sandbox.worker_main",
            ]
        )
        return argv


def _path_in_default_mounts(path: str) -> bool:
    """Is ``path`` inside one of isolate's built-in bind-mount roots?"""
    for root in _ISOLATE_DEFAULT_MOUNT_ROOTS:
        if path == root or path.startswith(root + os.sep):
            return True
    return False


def _python_prefix_mounts(python_exe: str) -> list[tuple[str, str, str]]:
    """Return ``extra_dirs`` entries that make ``python_exe`` reachable.

    isolate's default ``--dir`` rules cover ``/bin``, ``/lib``,
    ``/lib64``, and ``/usr``.  A Python interpreter installed by
    ``uv``, ``pyenv``, ``conda``, or any virtualenv outside ``/usr``
    is *not* visible in the chroot, so ``execve`` of that path fails
    with ``No such file or directory`` (exit 127).

    To make such an interpreter reachable we bind-mount its prefix
    -- e.g. ``~/.local/share/uv/python/cpython-3.12.X-...`` for a
    uv-managed python, or ``/env`` for the Gradescope grader venv --
    into the sandbox at the *same* host path.  Binding at the
    original path means the absolute ``python_executable`` argv
    string we already pass to ``--run`` resolves correctly inside
    the chroot, without any path rewriting.

    We deliberately do *not* follow symlinks when deciding whether
    a mount is needed: if the literal argv path lives outside
    ``/usr`` (e.g. a venv binary at ``/env/bin/python3.13`` that
    symlinks to ``/usr/bin/python3.13``), the chroot must still see
    the literal path so ``execve`` can resolve it.

    When the venv's interpreter symlinks to a base prefix that is
    *also* outside the default mounts (uv, pyenv, conda), we add a
    second mount for that prefix so the linker can find the stdlib
    and shared libraries.

    Returns an empty list if no extra mounts are needed.
    """
    if _path_in_default_mounts(python_exe):
        return []
    # Pick the smallest prefix that contains the executable.  When
    # the caller asks us to run the current interpreter we know it
    # is ``sys.prefix`` (the venv root, which contains the
    # ``bin/python`` entry the chroot must see).  Otherwise we fall
    # back to ascending two directories from the binary path
    # (``<prefix>/bin/python3`` -> ``<prefix>``).
    if sys.executable == python_exe:
        prefix = sys.prefix
    else:
        prefix = os.path.dirname(os.path.dirname(python_exe))
    # Mount at the same absolute path so the argv we pass to isolate
    # resolves inside the chroot.  isolate's ``--dir`` strips the
    # leading ``/`` for us (target is relative to the sandbox root).
    mounts: list[tuple[str, str, str]] = [(prefix.lstrip("/"), prefix, "")]
    # If the venv's base interpreter also lives outside the default
    # mounts (uv, pyenv, conda), expose it too -- the linker needs
    # to find ``libpython*.so`` and the stdlib under ``base_prefix``.
    if sys.executable == python_exe and sys.base_prefix != sys.prefix:
        base = sys.base_prefix
        if (
            not _path_in_default_mounts(base)
            and base != prefix
            and not base.startswith(prefix + os.sep)
            and not prefix.startswith(base + os.sep)
        ):
            mounts.append((base.lstrip("/"), base, ""))
    return mounts


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

    If ``python_executable`` (or ``sys.executable`` when omitted)
    lives outside isolate's default bind-mount roots, an extra
    ``--dir`` rule is added so the chroot can see and ``execve`` it.
    """
    time_limit = request.time_limit_seconds
    wall_limit = time_limit * DEFAULT_WALL_TIME_MULTIPLIER
    mem_mb = request.memory_limit_mb
    python_exe = python_executable or sys.executable
    all_extra_dirs = list(extra_dirs)
    for python_mount in _python_prefix_mounts(python_exe):
        if python_mount not in all_extra_dirs:
            all_extra_dirs.append(python_mount)
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
        extra_dirs=tuple(all_extra_dirs),
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
                # The worker only sees ``/submission`` (the bind
                # mount); rewrite ``submission_dir`` before encoding
                # so ``_patched_cwd_and_path`` chdirs to a path that
                # actually exists inside the sandbox.  The build_run_plan
                # call above used the host path to construct the mount
                # spec, which is exactly what's needed there.
                worker_request = replace(request, submission_dir=SANDBOX_SUBMISSION_DIR)
                stdin_bytes = _encode_request(worker_request)
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
