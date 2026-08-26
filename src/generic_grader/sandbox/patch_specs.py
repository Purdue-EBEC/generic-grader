"""Host-side helpers for building `PatchSpec` instances.

These mirror the existing `make_mock_function_*` helpers in
`generic_grader.utils.mocks`, but emit JSON-serializable
:class:`~generic_grader.sandbox.protocol.PatchSpec` records instead of
live ``(target, callable)`` tuples.  The same spec format is consumed
by both the in-process path (``custom_stack`` rebuilds a mock from the
spec) and the sandboxed path (the worker rebuilds the same mock inside
the sandbox).

Use these in tests where ``Options.use_sandbox=True`` is set, or for
new code that wants its patches to be sandbox-portable from day one.
"""

from __future__ import annotations

import inspect
import textwrap
from typing import Any, Callable

from generic_grader.sandbox.protocol import PatchSpec


def make_noop_patch_spec(
    target: str, *, patch_kwargs: dict[str, Any] | None = None
) -> PatchSpec:
    """Spec for a patch that replaces `target` with a no-op."""
    return PatchSpec(target=target, kind="noop", patch_kwargs=dict(patch_kwargs or {}))


def make_iter_patch_spec(
    target: str,
    values: list[Any],
    *,
    patch_kwargs: dict[str, Any] | None = None,
) -> PatchSpec:
    """Spec for a patch that yields successive `values` then raises.

    The reconstructed mock returns the next item in `values` on each
    call and raises ``ExcessFunctionCallError`` once `values` is
    exhausted, matching the existing :func:`make_mock_function` helper.
    """
    return PatchSpec(
        target=target,
        kind="iter_returns",
        values=list(values),
        patch_kwargs=dict(patch_kwargs or {}),
    )


def make_raise_error_patch_spec(
    target: str,
    error: type[BaseException],
    *,
    patch_kwargs: dict[str, Any] | None = None,
) -> PatchSpec:
    """Spec for a patch that raises `error` on every call.

    `error` must be importable by dotted path on the worker side; the
    spec serializes the qualified name (``module.Class``).
    """
    if not isinstance(error, type) or not issubclass(error, BaseException):
        raise TypeError(f"`error` must be an exception class; got {error!r}")
    qualname = f"{error.__module__}.{error.__qualname__}"
    return PatchSpec(
        target=target,
        kind="raise_error",
        error_qualname=qualname,
        patch_kwargs=dict(patch_kwargs or {}),
    )


def make_source_patch_spec(
    target: str,
    func: Callable[..., Any],
    *,
    patch_kwargs: dict[str, Any] | None = None,
) -> PatchSpec:
    """Spec for a patch defined by the source of a host-side function.

    The function's source is captured via :func:`inspect.getsource`
    and shipped to the worker, which exec's it in an empty namespace
    and pulls out the function by name.  This is the escape hatch for
    assignment-specific patches (e.g. a fake physics function) that
    don't fit one of the predefined templates.

    Restrictions
    ------------
    - `func` must be defined at module scope (or be otherwise
      retrievable by :func:`inspect.getsource`).
    - `func` may not be a closure: its source is executed in an empty
      namespace inside the sandbox, so it can't depend on any
      enclosing-scope variables.
    """
    if not callable(func):
        raise TypeError(f"`func` must be callable; got {func!r}")
    try:
        raw = inspect.getsource(func)
    except (OSError, TypeError) as e:
        raise ValueError(f"Cannot capture source for {func!r}: {e}") from e
    source = textwrap.dedent(raw)
    name = getattr(func, "__name__", None)
    if not name or name == "<lambda>":
        raise ValueError(
            "Patch source functions must have a real `__name__`; "
            "lambdas and anonymous functions can't cross the sandbox."
        )
    return PatchSpec(
        target=target,
        kind="source",
        source=source,
        name=name,
        patch_kwargs=dict(patch_kwargs or {}),
    )


__all__ = (
    "make_iter_patch_spec",
    "make_noop_patch_spec",
    "make_raise_error_patch_spec",
    "make_source_patch_spec",
)
