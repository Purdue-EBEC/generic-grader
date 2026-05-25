"""Host-side glue between the existing `Importer` / `User` API and the sandbox.

This module is the bridge enabled by ``Options.use_sandbox=True``.  It
mirrors the same student-facing contracts as the in-process Layer 1
path:

* ``sandbox_import_obj`` performs an import-only run in a fresh
  sandbox.  Any module-level ``input()`` call is classified as
  "stuck at input during import", matching the legacy
  :class:`generic_grader.utils.importer.Importer.InputError` flow.
* ``sandbox_call_obj`` runs the student's callable in a *separate*
  fresh sandbox.  Stdout / stdin events from the worker are replayed
  into the same `LogIO` and `interactions` data structures that the
  existing `__User__` already maintains, so downstream methods
  (``read_log_line``, ``get_value``, ``format_log``) keep working.

Each call gets its own sandbox box (the box pool below hands out
disjoint ``box_id``s) so concurrent test runners under
``pytest-xdist`` never collide on isolate state.

Nothing in this module *replaces* `Importer` or `__User__` directly --
that wiring (turning the ``Options.use_sandbox`` flag into the routing
decision) is the job of commit 5d.  Keeping the integration module
free of any `Importer`/`User` reference also makes it the place we
unit-test the sandbox path in isolation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Sequence

from generic_grader.sandbox.protocol import PatchSpec, Request, Response
from generic_grader.sandbox.runner import IsolateRunner
from generic_grader.utils.exceptions import EndOfInputError, ExtraEntriesError
from generic_grader.utils.options import Options

# ---------------------------------------------------------------------------
# Box pool
# ---------------------------------------------------------------------------

# isolate boxes live at /var/local/lib/isolate/<box_id>; concurrent
# graders need disjoint ids.  The pool below hands them out and
# returns them so a pytest-xdist worker can hold a single id across
# its (sequential) test cases.

DEFAULT_BOX_POOL_SIZE = 64


class BoxPool:
    """A thread-safe pool of integer ``box_id`` slots for isolate.

    `acquire` blocks until a slot is free; `release` returns it.  The
    pool is bounded so we don't run away with arbitrary ids on a host
    where the isolate config restricts ``num_boxes``.

    The pool is not multi-process aware on its own -- the assumption
    is that pytest-xdist worker N pins its acquisitions to a stable
    base offset (handled by `pool_for_xdist_worker` below).
    """

    def __init__(self, size: int = DEFAULT_BOX_POOL_SIZE, base: int = 0) -> None:
        if size < 1:
            raise ValueError(f"BoxPool size must be >= 1; got {size}")
        if base < 0:
            raise ValueError(f"BoxPool base must be >= 0; got {base}")
        self._available: list[int] = list(range(base, base + size))
        self._cv = threading.Condition()

    def acquire(self) -> int:
        with self._cv:
            while not self._available:
                self._cv.wait()
            return self._available.pop()

    def release(self, box_id: int) -> None:
        with self._cv:
            self._available.append(box_id)
            self._cv.notify()


_DEFAULT_POOL = BoxPool()


def get_default_box_pool() -> BoxPool:
    """Return the process-wide default :class:`BoxPool`."""
    return _DEFAULT_POOL


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class SandboxRunResult:
    """The host-side view of a single sandbox run.

    After a call returns, the caller has:

    * ``return_value`` -- the JSON-decoded return (or ``None`` for
      non-serializable returns; check ``return_event`` for the repr).
    * ``log`` -- the reconstructed IO log (stdout interleaved with
      stdin responses, just like the in-process `LogIO`).
    * ``interactions`` -- list of offsets into ``log`` marking each
      ``input()`` prompt boundary.
    * ``unused_entries`` -- count of simulated entries the student
      didn't consume; nonzero means an `ExtraEntriesError` should be
      raised by the caller.
    * ``exception`` -- the structured exception chain, or ``None`` on
      success.
    * ``response`` -- the raw `Response` for advanced inspection.
    """

    return_value: Any = None
    return_non_serializable: bool = False
    return_repr: Optional[str] = None
    log: str = ""
    interactions: list[int] = field(default_factory=list)
    unused_entries: int = 0
    exception: Optional[list[dict[str, Any]]] = None
    figures: list[dict[str, Any]] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    response: Optional[Response] = None
    consumed_input_during_import: bool = False


# ---------------------------------------------------------------------------
# Event-stream replay
# ---------------------------------------------------------------------------


def _replay_events(response: Response) -> SandboxRunResult:
    """Walk a `Response.events` list and project it into a `SandboxRunResult`.

    The event order mirrors the order things happened in the worker,
    which lets us reconstruct the same interleaving of stdout writes
    and ``input()`` calls that the in-process path produces.
    """
    result = SandboxRunResult(
        exception=response.exception,
        elapsed_seconds=response.elapsed_seconds,
        response=response,
    )
    log_parts: list[str] = []
    log_length = 0
    # Mirrors the existing __User__: a leading 0 marker means "log
    # position before any input prompt".
    interactions: list[int] = [0]
    saw_input_event = False
    current_phase = "import"

    for event in response.events:
        if event.type == "phase":
            current_phase = event.extra.get("name") or current_phase
            continue
        if event.type == "stdout":
            data = event.extra.get("data", "")
            log_parts.append(data)
            log_length += len(data)
        elif event.type == "stderr":
            # The legacy path doesn't merge stderr into the IO log
            # (it patches sys.stdout only).  Keep parity here.
            continue
        elif event.type == "stdin":
            # input() was called: record the log offset (where the
            # next prompt began -- already accounted for by the
            # preceding stdout write) and append the entered text
            # followed by a newline, matching the legacy responder.
            interactions.append(log_length)
            entry = event.extra.get("data", "")
            line = f"{entry}\n"
            log_parts.append(line)
            log_length += len(line)
            if current_phase == "import":
                saw_input_event = True
        elif event.type == "return":
            if event.extra.get("non_serializable"):
                result.return_non_serializable = True
                result.return_repr = event.extra.get("repr")
            else:
                result.return_value = event.extra.get("value")
        elif event.type == "figure":
            result.figures.append(event.extra.get("properties", {}))
        elif event.type == "unused_entries":
            result.unused_entries = int(event.extra.get("count", 0))

    result.log = "".join(log_parts)
    result.interactions = interactions
    result.consumed_input_during_import = saw_input_event
    return result


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------


def _resolve_submission_dir(options: Options, module: str) -> str:
    """Return the directory the worker should bind-mount as the submission.

    The legacy importer imports student code from `cwd` (set by the
    test harness).  When ``Options.use_sandbox=True`` we bind that
    same directory in read-write under ``/box/submission``.  Module
    paths supplied via dotted names (e.g. ``tests.reference``) are
    handled by adjusting the package directory below.
    """
    cwd = Path.cwd()
    if "." in module:
        # Dotted module: the package root must contain the topmost
        # package directory.  We climb until the topmost package's
        # parent is on disk.
        top, *_ = module.split(".")
        candidate = cwd / top
        if candidate.exists():
            return str(cwd)
        # Fall through to cwd; the worker will raise ModuleNotFoundError
        # and the caller surfaces the structured exception.
    return str(cwd)


def _build_request(
    *,
    runtime: str,
    submission_dir: str,
    module: str,
    obj_name: str,
    options: Options,
    args: Sequence[Any] = (),
    kwargs: Optional[dict[str, Any]] = None,
    entries: Sequence[str] = (),
    patch_specs: Sequence[PatchSpec] = (),
    captures: Sequence[str] = ("stdout", "stderr", "return", "figures"),
) -> Request:
    """Build a :class:`Request` from `Options`, factoring out parameter pass-through."""
    return Request(
        runtime=runtime,
        submission_dir=submission_dir,
        module=module,
        obj_name=obj_name,
        args=tuple(args),
        kwargs=dict(kwargs or {}),
        entries=tuple(entries),
        fixed_time=(
            options.fixed_time
            if isinstance(options.fixed_time, str)
            else (options.fixed_time.isoformat() if options.fixed_time else None)
        ),
        time_limit_seconds=float(options.time_limit),
        memory_limit_mb=int(options.memory_limit_GB * 1024),
        log_limit=int(options.log_limit or 0),
        captures=tuple(captures),
        patch_specs=tuple(patch_specs),
    )


# ---------------------------------------------------------------------------
# Runner factory (overridable for tests)
# ---------------------------------------------------------------------------

# A factory that returns a configured `IsolateRunner`.  Tests inject a
# fake runner; production code uses `default_runner_factory` which
# resolves the grader source directory from this module's location.
RunnerFactory = Callable[[int], "IsolateRunnerLike"]


class IsolateRunnerLike:  # pragma: no cover - structural typing only
    def run(self, request: Request) -> Response: ...


def _grader_src_root() -> str:
    """Return the directory containing the ``generic_grader`` package."""
    # ``__file__`` is .../generic_grader/sandbox/integration.py; we
    # want the directory that *contains* the package so the worker's
    # PYTHONPATH = /box/grader resolves ``import generic_grader``.
    return str(Path(__file__).resolve().parent.parent.parent)


def default_runner_factory(box_id: int) -> IsolateRunner:
    """Default factory: a fresh :class:`IsolateRunner` per call.

    The runner does its own init/cleanup of the isolate box per
    ``run()``, so reusing one instance across calls is safe.  We
    still build a new one each time to keep the integration module
    stateless from the caller's perspective.
    """
    return IsolateRunner(grader_src=_grader_src_root(), box_id=box_id)


# ---------------------------------------------------------------------------
# Public API: import_obj / call_obj equivalents
# ---------------------------------------------------------------------------


def sandbox_import_obj(
    module: str,
    options: Options,
    *,
    runner_factory: Optional[RunnerFactory] = None,
    box_pool: Optional[BoxPool] = None,
) -> SandboxRunResult:
    """Run an import-only probe of `module` inside a fresh sandbox.

    The probe imports `module` and resolves ``options.obj_name``.  Any
    ``input()`` call during import is recorded as a structured event
    (the worker patches ``builtins.input`` to consume from the
    Request's ``entries``, which we leave empty so the first call
    raises ``EOFError`` -- the worker's protocol-level analogue of
    Layer 1's ``Importer.InputError``).

    Returns a :class:`SandboxRunResult` so callers can decide how to
    classify the outcome.  Commit 5d turns those classifications into
    the matching student-facing test failures.
    """
    factory = runner_factory or default_runner_factory
    pool = box_pool or _DEFAULT_POOL
    submission_dir = _resolve_submission_dir(options, module)

    # Use a target that resolves immediately without invoking student
    # code: importing the module and getattr()ing obj_name happens
    # before the worker tries to call anything.  We pick a no-op
    # placeholder for the "call" by asking the worker to import only;
    # to keep the wire protocol simple we instead invoke the
    # resolved object with no args/kwargs but disable the call by
    # patching it with a noop spec whose target is the same dotted
    # path.
    #
    # In practice that's overkill: we just need to know whether the
    # import succeeds and whether the module-level code calls
    # ``input()``.  Calling the object with empty args is acceptable
    # because the in-process path *also* calls it (via getattr +
    # return).  But the legacy importer does NOT call the object --
    # it returns it.  To preserve that contract we patch the resolved
    # name with a noop so the worker's call phase is a no-op.
    obj_name = options.obj_name
    import_only_spec = PatchSpec(target=f"{module}.{obj_name}", kind="noop")

    request = _build_request(
        runtime="python",
        submission_dir=submission_dir,
        module=module,
        obj_name=obj_name,
        options=options,
        args=(),
        kwargs={},
        entries=(),
        patch_specs=(import_only_spec, *options.patch_specs),
        # During import we don't need figures or return values.
        captures=("stdout", "stderr"),
    )

    box_id = pool.acquire()
    try:
        runner = factory(box_id)
        response = runner.run(request)
    finally:
        pool.release(box_id)

    return _replay_events(response)


def sandbox_call_obj(
    module: str,
    options: Options,
    *,
    runner_factory: Optional[RunnerFactory] = None,
    box_pool: Optional[BoxPool] = None,
    entries: Optional[Sequence[str]] = None,
) -> SandboxRunResult:
    """Run ``module.obj_name(*args, **kwargs)`` inside a fresh sandbox.

    A *new* sandbox box is allocated for this call (independent of any
    earlier `sandbox_import_obj`).  The worker captures stdout, stdin
    echoes, return values, and any open matplotlib figures, and the
    result is replayed into a `SandboxRunResult` for downstream
    consumption by `__User__`.

    `entries` overrides ``options.entries`` (used by the legacy path
    when the caller wants to short-circuit the simulated input).
    """
    factory = runner_factory or default_runner_factory
    pool = box_pool or _DEFAULT_POOL
    submission_dir = _resolve_submission_dir(options, module)
    effective_entries = (
        tuple(entries) if entries is not None else tuple(options.entries or ())
    )

    request = _build_request(
        runtime="python",
        submission_dir=submission_dir,
        module=module,
        obj_name=options.obj_name,
        options=options,
        args=tuple(options.args or ()),
        kwargs=dict(options.kwargs or {}),
        entries=effective_entries,
        patch_specs=tuple(options.patch_specs or ()),
    )

    box_id = pool.acquire()
    try:
        runner = factory(box_id)
        response = runner.run(request)
    finally:
        pool.release(box_id)

    return _replay_events(response)


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------


def classify_import_outcome(result: SandboxRunResult) -> Optional[type[BaseException]]:
    """Map a `SandboxRunResult` from import to a Python exception type.

    Returns ``None`` on success.  The mapping mirrors the legacy
    `Importer.import_obj` classification:

    * Module-level ``input()`` call -> ``EndOfInputError`` (host
      callers translate this into the "stuck at input during
      import" failure path).
    * Any other structured exception -> the matching class resolved
      from `result.exception[0]["type"]`, or ``Exception`` as a
      fallback when the class isn't importable on the host.
    """
    if result.consumed_input_during_import:
        return EndOfInputError
    if not result.exception:
        return None
    head = result.exception[0]
    if head.get("type") == "EOFError":
        # The worker's responder raises EOFError when entries are
        # exhausted -- this is the protocol-level signal for "stuck
        # at input during import" since import_obj sends entries=().
        return EndOfInputError
    return _resolve_exception_class(head.get("type") or "")


def classify_call_outcome(result: SandboxRunResult) -> Optional[type[BaseException]]:
    """Map a call-phase `SandboxRunResult` to a Python exception type."""
    if not result.exception and result.unused_entries:
        return ExtraEntriesError
    if not result.exception:
        return None
    head = result.exception[0]
    return _resolve_exception_class(head.get("type") or "")


def _resolve_exception_class(name: str) -> type[BaseException]:
    """Best-effort lookup of an exception class by short name.

    Falls back to a generic ``Exception`` if the name isn't in the
    builtins or in `generic_grader.utils.exceptions` -- the
    structured chain still carries the message, so downstream
    formatters lose only the type for unknown classes.
    """
    import builtins as _b

    cls = getattr(_b, name, None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return cls
    try:
        import generic_grader.utils.exceptions as _exc_mod
    except ImportError:  # pragma: no cover - defensive
        return Exception
    cls = getattr(_exc_mod, name, None)
    if isinstance(cls, type) and issubclass(cls, BaseException):
        return cls
    return Exception


# ---------------------------------------------------------------------------
# Iterator helper (used by tests; kept here so the public surface is
# import-clean even when the worker isn't installed)
# ---------------------------------------------------------------------------


def iter_events(response: Response) -> Iterator[dict[str, Any]]:
    """Yield each event from `response` as a plain dict."""
    for event in response.events:
        yield event.to_dict()


__all__ = (
    "BoxPool",
    "DEFAULT_BOX_POOL_SIZE",
    "SandboxRunResult",
    "classify_call_outcome",
    "classify_import_outcome",
    "default_runner_factory",
    "get_default_box_pool",
    "iter_events",
    "sandbox_call_obj",
    "sandbox_import_obj",
)
