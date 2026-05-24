"""Python runtime worker for the sandboxed grader.

Responsibilities
----------------

* Resolve `Request.module:Request.obj_name` from `Request.submission_dir`.
* Patch ``sys.stdout`` / ``sys.stderr`` to emit framed `Event` records.
* Patch ``builtins.input`` to pull from a queue of simulated entries,
  emitting one ``stdin`` event per consumed entry.
* Call the resolved object and emit a ``return`` event with the
  result (or, for non-JSON-serializable returns, a ``repr`` flagged event).
* If anything raises (during import or during the call), walk the
  ``__cause__`` / ``__context__`` chain, build a structured list of
  ``{type, message, traceback}`` dicts, and stash it on the response.
* Filter traceback frames to files inside ``submission_dir`` so the
  worker never reveals grader internals to the student.

The worker does **not** perform sandbox isolation itself — that is the
job of the runner in `runner.py` (commit 4), which spawns the worker
under ``isolate``.  This module is in-process so it can be unit
tested directly and so the same code runs both at test time and
inside the real sandbox.
"""

from __future__ import annotations

import builtins
import importlib
import io
import json
import os
import sys
import time
import traceback
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from generic_grader.sandbox.protocol import Event, Request, Response

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Frames whose filename resolves under any of these roots are considered
# "grader frames" and stripped from serialized tracebacks before they
# cross the wire.  We compute these once at import time.
_GRADER_ROOTS: tuple[str, ...] = tuple(
    sorted(
        {
            str(Path(__file__).resolve().parent.parent),
        }
    )
)


def _is_grader_frame(frame_filename: str) -> bool:
    """Return True if `frame_filename` is inside the grader's own source."""
    if not frame_filename:
        return False
    try:
        resolved = str(Path(frame_filename).resolve())
    except (OSError, ValueError):
        resolved = frame_filename
    return any(resolved.startswith(root) for root in _GRADER_ROOTS)


# ---------------------------------------------------------------------------
# Stream wrappers
# ---------------------------------------------------------------------------


class _EventStream(io.TextIOBase):
    """A text stream that funnels every write into an event sink.

    Each `write` call appends an Event of the configured type to the
    shared `events` list.  Empty writes are dropped so that
    ``print("x")`` (which writes ``"x"`` and ``"\\n"`` separately on
    some Python versions) doesn't produce zero-length events.
    """

    def __init__(self, events: list[Event], event_type: str) -> None:
        super().__init__()
        self._events = events
        self._event_type = event_type

    # TextIOBase already provides a `flush` no-op, which is what we want.

    def writable(self) -> bool:  # pragma: no cover - trivial
        return True

    def write(self, s: str) -> int:
        if s:
            self._events.append(Event(type=self._event_type, data=s))
        return len(s)


# ---------------------------------------------------------------------------
# input() replacement
# ---------------------------------------------------------------------------


class _Responder:
    """Callable that mimics the builtin ``input`` against an entries queue.

    * Each call writes the prompt to the stdout sink (preserving the
      ``print("prompt", end="")`` behavior of the real input).
    * Each call emits a `stdin` event with the consumed entry.
    * Running out of entries raises `EOFError` (the same exception
      Python raises on EOF in real `input()`), letting host code
      classify the failure.
    """

    def __init__(
        self,
        events: list[Event],
        entries: Iterator[str],
        stdout_sink: _EventStream | None,
    ) -> None:
        self._events = events
        self._entries = entries
        self._stdout = stdout_sink
        self.consumed = 0

    def __call__(self, prompt: str = "") -> str:
        # Echo the prompt through whatever the current stdout is so the
        # event log mirrors real terminal interaction.
        if prompt and self._stdout is not None:
            self._stdout.write(str(prompt))
        try:
            entry = next(self._entries)
        except StopIteration as e:
            raise EOFError("EOF when reading a line") from e
        entry = str(entry)
        self._events.append(Event(type="stdin", data=entry))
        self.consumed += 1
        return entry


# ---------------------------------------------------------------------------
# Return-value serialization
# ---------------------------------------------------------------------------


def _make_return_event(value: Any) -> Event:
    """Build a `return` event whose payload is safe to JSON-serialize.

    JSON-safe values are passed through verbatim. Anything else is
    rendered via ``repr()`` with a ``non_serializable`` flag so the
    host can distinguish the two cases.
    """
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return Event(type="return", non_serializable=True, repr=repr(value))
    return Event(type="return", value=value)


# ---------------------------------------------------------------------------
# Exception serialization
# ---------------------------------------------------------------------------


def _serialize_traceback(tb_summary: traceback.StackSummary) -> str:
    """Render a StackSummary as text, dropping any grader frames."""
    student_frames = [f for f in tb_summary if not _is_grader_frame(f.filename)]
    if not student_frames:
        # Nothing to show without exposing grader internals; keep the
        # student aware that frames were elided rather than leaking them.
        return "  (no student frames in traceback)\n"
    return "".join(traceback.StackSummary.from_list(student_frames).format())


def _serialize_exception_chain(exc: BaseException) -> list[dict[str, Any]]:
    """Walk an exception's cause/context chain and return a serialized list.

    The list is ordered from outermost (the exception actually raised)
    to innermost (its root cause).  Each entry carries:

    * ``type``: the exception class's qualified name.
    * ``message``: ``str(exc)``.
    * ``traceback``: the formatted traceback, filtered to student frames.
    """
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        tb_summary = traceback.extract_tb(current.__traceback__)
        chain.append(
            {
                "type": type(current).__name__,
                "message": str(current),
                "traceback": _serialize_traceback(tb_summary),
            }
        )
        current = current.__cause__ or current.__context__
    return chain


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


@contextmanager
def _patched_cwd_and_path(submission_dir: str):
    """Run a block with cwd and sys.path pointing at the submission dir."""
    original_cwd = os.getcwd()
    original_path = list(sys.path)
    original_modules = set(sys.modules)
    try:
        os.chdir(submission_dir)
        sys.path.insert(0, submission_dir)
        yield
    finally:
        # Remove anything imported during the run so a subsequent call
        # with a different submission_dir doesn't get the cached module.
        for name in set(sys.modules) - original_modules:
            sys.modules.pop(name, None)
        sys.path[:] = original_path
        try:
            os.chdir(original_cwd)
        except OSError:  # pragma: no cover - host cwd vanished
            pass


def _import_target(module: str, obj_name: str) -> Any:
    """Import `module` and return its `obj_name` attribute."""
    mod = importlib.import_module(module)
    return getattr(mod, obj_name)


# ---------------------------------------------------------------------------
# fixed_time / freezegun
# ---------------------------------------------------------------------------


@contextmanager
def _maybe_freeze_time(fixed_time: str | None):
    if not fixed_time:
        yield
        return
    # Imported lazily so the worker can run in environments where
    # freezegun is unavailable (e.g. minimal Octave installs later).
    from freezegun import freeze_time

    with freeze_time(fixed_time):
        yield


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_request(request: Request) -> Response:
    """Run a single `Request` and return a `Response`.

    This function is the worker's only public API.  It is intentionally
    synchronous and pure (no daemon thread, no global state mutation
    beyond the patches it explicitly applies and reverts) so the
    isolate runner can simply ``read_request(stdin) -> run_request ->
    write_response(stdout)`` and exit.
    """
    captures = set(request.captures or ())
    events: list[Event] = []
    exception_chain: list[dict[str, Any]] | None = None
    phase = "import"
    start = time.perf_counter()

    def _push_phase(name: str) -> None:
        events.append(Event(type="phase", name=name))

    # Pre-compose stream sinks so the input responder can echo prompts
    # into the same stdout the student would write to.
    stdout_sink = _EventStream(events, "stdout") if "stdout" in captures else None
    stderr_sink = _EventStream(events, "stderr") if "stderr" in captures else None

    entries_iter: Iterator[str] = iter(request.entries or ())
    responder = _Responder(events, entries_iter, stdout_sink)

    with ExitStack() as stack:
        stack.enter_context(_patched_cwd_and_path(request.submission_dir))
        stack.enter_context(_maybe_freeze_time(request.fixed_time))

        # Patch stdout / stderr / input via plain attribute swap (cheaper
        # and more deterministic than unittest.mock.patch in-process).
        if stdout_sink is not None:
            original_stdout = sys.stdout
            sys.stdout = stdout_sink  # type: ignore[assignment]
            stack.callback(setattr, sys, "stdout", original_stdout)
        if stderr_sink is not None:
            original_stderr = sys.stderr
            sys.stderr = stderr_sink  # type: ignore[assignment]
            stack.callback(setattr, sys, "stderr", original_stderr)

        original_input = builtins.input
        builtins.input = responder  # type: ignore[assignment]
        stack.callback(setattr, builtins, "input", original_input)

        try:
            target = _import_target(request.module, request.obj_name)
        except BaseException as e:  # noqa: BLE001 - report any import error
            exception_chain = _serialize_exception_chain(e)
        else:
            phase = "call"
            try:
                returned = target(*tuple(request.args or ()), **(request.kwargs or {}))
            except BaseException as e:  # noqa: BLE001 - report any student error
                exception_chain = _serialize_exception_chain(e)
            else:
                if "return" in captures:
                    events.append(_make_return_event(returned))

    # After the patches have been torn down we can safely emit
    # bookkeeping events without polluting the student's stream.
    if exception_chain is None:
        phase = "completed"
        # Count any entries the student didn't consume.
        leftover = list(entries_iter)
        if leftover:
            events.append(Event(type="unused_entries", count=len(leftover)))

    # Serialize any open matplotlib figures so plot tests can inspect
    # them on the host side. We always close figures afterwards so the
    # next in-process run starts clean -- the isolate runner spawns a
    # fresh worker per test, but unit tests reuse this process.
    if "figures" in captures:
        try:
            # Imported lazily so non-plot tests don't pay the matplotlib
            # startup cost and runtimes without matplotlib still work.
            from generic_grader.sandbox.figure_serializer import (
                serialize_current_figures,
            )

            for fig_dict in serialize_current_figures():
                events.append(Event(type="figure", properties=fig_dict))
        except ImportError:
            pass
    else:
        # Even when figures aren't captured, close any open figures
        # so they don't leak into the next call.
        try:
            import matplotlib.pyplot as _plt

            _plt.close("all")
        except ImportError:
            pass

    _push_phase(phase)

    elapsed = time.perf_counter() - start
    return Response(events=events, exception=exception_chain, elapsed_seconds=elapsed)


__all__ = ("run_request",)
