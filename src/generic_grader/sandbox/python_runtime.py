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
import re
import signal
import sys
import time
import traceback
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest.mock import patch as _mock_patch

from generic_grader.sandbox.protocol import Event, PatchSpec, Request, Response

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
        except StopIteration:
            # Match CPython's real ``input()`` semantics, which raise a
            # bare EOFError when stdin is exhausted with no chained
            # ``StopIteration`` polluting the visible cause chain.
            raise EOFError("EOF when reading a line") from None
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


_MAX_EXCEPTION_CHAIN_LINKS = 20


def _serialize_exception_chain(exc: BaseException) -> list[dict[str, Any]]:
    """Walk an exception's cause/context chain and return a serialized list.

    The list is ordered from outermost (the exception actually raised)
    to innermost (its root cause).  Each entry carries:

    * ``type``: the exception class's qualified name.
    * ``message``: ``str(exc)``.
    * ``traceback``: the formatted traceback, filtered to student frames.

    Cycle protection uses both an ``id()`` set and a hard depth cap
    (``_MAX_EXCEPTION_CHAIN_LINKS``).  In practice the chain is kept
    alive by ``current`` so ``id()`` reuse is impossible inside the
    loop, but the depth cap is a cheap belt-and-suspenders guard
    against pathological user-constructed cycles.
    """
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while (
        current is not None
        and id(current) not in seen
        and len(chain) < _MAX_EXCEPTION_CHAIN_LINKS
    ):
        seen.add(id(current))
        tb_summary = traceback.extract_tb(current.__traceback__)
        chain.append(
            {
                "type": type(current).__name__,
                "message": str(current),
                "traceback": _serialize_traceback(tb_summary),
            }
        )
        # Walk the chain the same way CPython's traceback printer does:
        # ``__cause__`` always wins, otherwise ``__context__`` --
        # unless ``__suppress_context__`` is set (which is what
        # ``raise X from None`` does to hide an implicit context).
        next_exc = current.__cause__
        if next_exc is None and not current.__suppress_context__:
            next_exc = current.__context__
        current = next_exc
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


# Dotted Python identifier, e.g. ``submission`` or ``pkg.submission``.
_MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_OBJ_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _import_target(module: str, obj_name: str) -> Any:
    """Import `module` and return its `obj_name` attribute.

    Raises ``ValueError`` if either name fails the Python-identifier
    syntax check.  Defense in depth: the host always sets these from
    `Options` (which themselves come from grader code), but the worker
    is also reached directly in tests and we don't want a malformed
    request to feed arbitrary input into ``importlib.import_module``.
    """
    if not _MODULE_NAME_RE.match(module):
        raise ValueError(
            f"Invalid module name {module!r}; expected a dotted Python identifier."
        )
    if not _OBJ_NAME_RE.match(obj_name):
        raise ValueError(
            f"Invalid object name {obj_name!r}; expected a Python identifier."
        )
    mod = importlib.import_module(module)
    return getattr(mod, obj_name)


# ---------------------------------------------------------------------------
# Patch reconstruction
# ---------------------------------------------------------------------------

# Dotted Python path matching ``module(.sub)*.attribute``.  This is
# intentionally stricter than the module-name regex above because we
# need at least one ``.`` to separate the target attribute from its
# enclosing module.
_PATCH_TARGET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_ERROR_QUALNAME_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"
)


def _target_basename(target: str) -> str:
    """Return the trailing attribute of a dotted patch target.

    The student-facing error messages built inside the reconstructed
    mocks only need the short name (e.g. ``"input"`` from
    ``"submission.input"``), matching the behavior of the host-side
    :func:`generic_grader.utils.mocks.make_mock_function` helper.
    """
    return target.rsplit(".", 1)[-1]


def _resolve_error_class(qualname: str) -> type[BaseException]:
    """Resolve a dotted ``module.Class`` path to an exception class.

    Used by the ``raise_error`` patch kind so the host can ship just
    the qualified name across the wire instead of a pickled class.
    """
    if not _ERROR_QUALNAME_RE.match(qualname):
        raise ValueError(
            f"Invalid error_qualname {qualname!r}; expected a dotted Python path."
        )
    module_name, _, attr = qualname.rpartition(".")
    module = importlib.import_module(module_name)
    cls = getattr(module, attr)
    if not isinstance(cls, type) or not issubclass(cls, BaseException):
        raise TypeError(
            f"{qualname} resolved to {cls!r}, which is not an exception class."
        )
    return cls


def _build_mock_from_spec(spec: PatchSpec) -> Callable[..., Any]:
    """Reconstruct the callable described by a :class:`PatchSpec`.

    Each kind maps to one of the host-side mock templates in
    :mod:`generic_grader.utils.mocks`, but rebuilt locally inside the
    worker so we never have to ship a live closure across the sandbox
    boundary.  The fourth kind, ``source``, exec's a host-supplied
    function source in an empty namespace -- this is the escape hatch
    used for assignment-specific patches (e.g. a fake physics
    function).  Running the exec in an empty namespace means the
    source can't depend on any host-side variables and can't observe
    the grader's own module globals.
    """
    if spec.kind == "noop":

        def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        return _noop

    if spec.kind == "iter_returns":
        # Avoid `deepcopy` (used by the host-side helper) because we
        # already crossed JSON, so each element is a fresh primitive.
        iterator = iter(list(spec.values))
        # Import lazily so an unrelated import failure in
        # generic_grader.utils.exceptions can't break worker startup.
        from generic_grader.utils.exceptions import ExcessFunctionCallError

        basename = _target_basename(spec.target)

        def _iter_returns(*args: Any, **kwargs: Any) -> Any:
            try:
                return next(iterator)
            except StopIteration as e:
                raise ExcessFunctionCallError(basename) from e

        return _iter_returns

    if spec.kind == "raise_error":
        error_cls = _resolve_error_class(spec.error_qualname or "")
        from generic_grader.utils.docs import make_call_str

        basename = _target_basename(spec.target)

        def _raise(*args: Any, **kwargs: Any) -> Any:
            call_str = make_call_str(basename, args, kwargs)
            raise error_cls(f"Your program unexpectedly called `{call_str}`.")

        return _raise

    # spec.kind == "source" (validated in PatchSpec.__post_init__)
    namespace: dict[str, Any] = {}
    # The source string was captured with `inspect.getsource` on the
    # host (already dedented) and is treated here as an isolated
    # function definition: no access to grader globals, no builtins
    # mutation, no shared state.
    exec(compile(spec.source or "", "<patch_spec>", "exec"), namespace)
    func = namespace.get(spec.name or "")
    if not callable(func):
        raise ValueError(
            f"PatchSpec source did not define a callable named {spec.name!r}."
        )
    return func


def _enter_patches_from_specs(stack: ExitStack, specs: tuple[PatchSpec, ...]) -> None:
    """Apply each :class:`PatchSpec` via ``unittest.mock.patch`` on `stack`.

    The patches are reverted automatically when ``stack`` unwinds, so
    the worker's runtime state is clean by the time we serialize the
    response.
    """
    for spec in specs:
        if not _PATCH_TARGET_RE.match(spec.target):
            raise ValueError(
                f"Invalid patch target {spec.target!r}; expected a dotted path."
            )
        mock_fn = _build_mock_from_spec(spec)
        kwargs = dict(spec.patch_kwargs or {})
        stack.enter_context(_mock_patch(spec.target, new=mock_fn, **kwargs))


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


@contextmanager
def _student_call_time_limit(seconds: float):
    """Wrap the student call in a ``SIGALRM`` alarm matching legacy semantics.

    The legacy non-sandbox path (`generic_grader.utils.resource_limits.
    time_limit`) wraps *only* the student's call in a ``signal.alarm``,
    not interpreter startup or grader-side imports.  We mirror that
    here so ``Request.time_limit_seconds`` keeps its original meaning:
    the budget for student code, with interpreter / import cost free.

    Isolate's outer ``--time`` limit still applies as a hard safety
    net (set by the runner to ``time_limit + STARTUP_OVERHEAD_SECONDS``),
    so genuinely runaway processes are still killed -- they just get
    a structured ``UserTimeoutError`` first when their student code
    overruns its budget.

    Uses ``signal.setitimer`` (not ``signal.alarm``) so fractional
    budgets work; ``signal.alarm`` would silently truncate ``0.5``
    seconds to ``0`` (disabling the alarm).

    A non-positive ``seconds`` value disables the alarm entirely.
    """
    if seconds <= 0:
        yield
        return

    # Imported lazily so non-sandbox code paths that re-import this
    # module (e.g. unit tests) don't pull in the full grader package
    # just to exercise the worker dispatch.
    from generic_grader.utils.exceptions import UserTimeoutError

    def _handler(signum, frame):  # pragma: no cover - exercised via signal
        raise UserTimeoutError(
            f"The time limit for this test is {seconds:g}"
            + (" second." if seconds == 1 else " seconds.")
        )

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        # Cancel any pending alarm and restore the previous handler
        # so a leftover timer can't fire later (e.g. during figure
        # serialization on the way out of ``run_request``).
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


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

    # Cheap unconditional checkpoint log -- one ``perf_counter`` call
    # per major phase.  The host's profile writer (see ``runner.py``,
    # ``GENERIC_GRADER_PROFILE``) merges this list into its JSON line
    # when profiling is enabled, and ignores it otherwise.  Keeping
    # the worker side unconditional means the host doesn't have to
    # propagate an env var across the sandbox boundary.
    checkpoints: list[tuple[str, float]] = [("enter", 0.0)]

    def _checkpoint(name: str) -> None:
        checkpoints.append((name, time.perf_counter() - start))

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

        # Patches must be active across both the import (so module-level
        # code that calls the patched target sees the mock) and the
        # subsequent call.  Any error building/installing patches is
        # treated like an import-time error so the host sees a
        # structured exception chain rather than the worker crashing.
        try:
            _enter_patches_from_specs(stack, tuple(request.patch_specs or ()))
        except BaseException as e:  # noqa: BLE001 - report patch errors
            exception_chain = _serialize_exception_chain(e)
        else:
            _checkpoint("patches_installed")
            try:
                target = _import_target(request.module, request.obj_name)
            except BaseException as e:  # noqa: BLE001 - report any import error
                exception_chain = _serialize_exception_chain(e)
            else:
                _checkpoint("import_target")
                phase = "call"
                try:
                    # ``Request.time_limit_seconds`` is the student-code
                    # budget (legacy ``Options.time_limit`` semantics).
                    # Isolate's outer ``--time`` flag is a wider safety
                    # net; this alarm matches the legacy non-sandbox
                    # ``resource_limits.time_limit`` behavior so timed
                    # tests look the same to assignments regardless
                    # of which runtime path executes them.
                    with _student_call_time_limit(request.time_limit_seconds):
                        returned = target(
                            *tuple(request.args or ()), **(request.kwargs or {})
                        )
                except BaseException as e:  # noqa: BLE001 - report any student error
                    exception_chain = _serialize_exception_chain(e)
                else:
                    if "return" in captures:
                        events.append(_make_return_event(returned))
                _checkpoint("call_returned")

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
    _checkpoint("figures_start")
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

    _checkpoint("figures_done")
    _push_phase(phase)
    _checkpoint("completed")
    events.append(Event(type="profile", checkpoints=checkpoints))

    elapsed = time.perf_counter() - start
    return Response(events=events, exception=exception_chain, elapsed_seconds=elapsed)


__all__ = ("run_request",)
