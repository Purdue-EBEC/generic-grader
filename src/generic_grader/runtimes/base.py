"""Runtime interface used by :mod:`generic_grader.utils.user`.

Every language-specific runtime implements the same two operations:

* ``resolve(test, options, module)`` — locate the student/reference
  target ``options.obj_name`` inside ``module``.  For the Python runtime
  this is ``__import__``; for the Octave runtime it is a filesystem
  lookup for ``module.m``.  The runtime may fail the
  :class:`unittest.TestCase` with a student-facing message via
  ``test.fail(...)`` (the Python runtime already does this via
  :class:`~generic_grader.utils.importer.Importer` and we preserve that
  behavior).  On success it returns an opaque *handle* that is passed
  unchanged to :meth:`Runtime.run` — the caller does not introspect it.

* ``run(options, handle, log, entries)`` — execute the resolved target.
  Return a :class:`RuntimeResult` on success; raise a Python exception
  on runtime error (student ``ZeroDivisionError``, an Octave error, a
  time-limit hit, ...).  The exception is intercepted by
  :func:`generic_grader.utils.user.__User__.call_obj`, which owns the
  student-facing error formatting and I/O log rendering — the runtime
  does *not* need to duplicate that logic.

The runtime is also responsible for:

* Wiring simulated stdin from ``entries`` (Python: patched
  ``builtins.input``; Octave: piped ``stdin`` fed line by line).
* Writing anything the target prints to ``log`` (Python: patched
  ``sys.stdout``; Octave: subprocess stdout tee'd into ``log``).
* Enforcing ``options.time_limit`` and ``options.memory_limit_GB``
  (Python: :func:`~generic_grader.utils.resource_limits.time_limit` and
  :func:`~generic_grader.utils.resource_limits.memory_limit` via
  :func:`~generic_grader.utils.patches.custom_stack`; Octave:
  ``preexec_fn`` + ``subprocess.communicate(timeout=...)``).

The interface is intentionally narrow — anything more (e.g. per-runtime
tear-down) belongs inside the concrete class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from unittest import TestCase

from generic_grader.utils.options import Options


@dataclass(frozen=True)
class RuntimeResult:
    """Language-agnostic result of a single :meth:`Runtime.run` call.

    Attributes:
        returned_values: Whatever the target returned when called
            (``None`` for scripts or for tests that only compare
            printed output).  Kept as ``Any`` because Python functions
            return arbitrary objects and Octave return values are
            decoded into native Python objects (numbers, strings, or
            tuples of the same) in follow-on PRs.
        artifacts: Optional bag of extra runtime-specific values that a
            future test type may consume (e.g. serialized figures for
            plot tests).  Not used by the initial output-lines PR.
    """

    returned_values: Any = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Runtime(Protocol):
    """Structural protocol every language runtime must satisfy.

    We use a :class:`Protocol` (rather than an :class:`abc.ABC`) so
    runtimes can be lightweight modules with no forced base class, and
    so ``isinstance`` checks in tests remain optional.
    """

    #: Human-readable name used in error messages (``"Python"``,
    #: ``"Octave"``, ...).
    name: str

    def resolve(self, test: TestCase, options: Options, module: str) -> Any:
        """See module docstring."""
        ...

    def run(
        self,
        options: Options,
        handle: Any,
        log,
        entries,
    ) -> RuntimeResult:
        """See module docstring."""
        ...


__all__ = ("Runtime", "RuntimeResult")
