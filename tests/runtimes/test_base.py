"""Unit tests for the language-neutral runtime plumbing.

These tests intentionally exercise the *contract* of
:mod:`generic_grader.runtimes.base` and the small registry in
:mod:`generic_grader.runtimes.__init__` without touching any concrete
runtime.  Doing so lets us catch regressions in the seam that adding a
third language (say ``python2`` or ``matlab``) would rely on, without
those regressions being masked by parallel changes in a specific
backend.
"""

from __future__ import annotations

import pytest

from generic_grader.runtimes import RUNTIMES, get_runtime
from generic_grader.runtimes.base import Runtime, RuntimeResult
from generic_grader.runtimes.octave import OctaveRuntime
from generic_grader.runtimes.python import PythonRuntime


def test_runtime_result_is_frozen_dataclass():
    """``RuntimeResult`` must be immutable.

    The result crosses the runtime → :class:`__User__` boundary; if a
    consumer could mutate it we'd risk one test's returned value
    bleeding into the next.  Freezing the dataclass makes that a
    ``FrozenInstanceError`` at the point of the bug rather than a
    silent, cross-test failure.
    """
    result = RuntimeResult(returned_values=42)
    assert result.returned_values == 42
    # Default artifacts is an empty dict — each instance gets its own
    # via ``field(default_factory=dict)`` so there is no shared
    # mutable default.
    assert result.artifacts == {}
    other = RuntimeResult(returned_values=None)
    assert other.artifacts is not result.artifacts

    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        result.returned_values = 99  # type: ignore[misc]


def test_runtime_result_accepts_artifacts_tuple():
    """Artifacts are pass-through data for later PRs (plot outputs,
    generated files, etc.).  Confirm the field round-trips."""
    result = RuntimeResult(returned_values=None, artifacts={"plots": ["plot.png"]})
    assert result.artifacts == {"plots": ["plot.png"]}


def test_registry_contains_python_and_octave():
    """The registry is what the ``Options.language`` validator reads
    to decide which strings are legal, so it must at minimum name
    both backends we ship with."""
    assert set(RUNTIMES) >= {"python", "octave"}
    assert RUNTIMES["python"] is PythonRuntime
    assert RUNTIMES["octave"] is OctaveRuntime


def test_get_runtime_returns_class_for_known_language():
    """``get_runtime`` is the single lookup helper used by
    ``__User__.__init__``.  Return values must be the runtime *class*
    (the caller instantiates it) — not a pre-built instance, since
    each ``__User__`` needs its own runtime state."""
    assert get_runtime("python") is PythonRuntime
    assert get_runtime("octave") is OctaveRuntime


def test_get_runtime_rejects_unknown_language():
    """Unknown languages must be rejected loudly.  This is defense in
    depth — ``Options`` validates the string too, but a caller
    constructing a runtime directly (e.g. from a plugin) still needs
    a clear error."""
    with pytest.raises(KeyError):
        get_runtime("cobol")


def test_runtime_protocol_is_a_protocol():
    """``Runtime`` is a :class:`typing.Protocol` so third-party
    plugins can duck-type it without inheriting.  The concrete
    runtimes we ship should still satisfy ``isinstance`` under
    ``@runtime_checkable`` semantics."""
    assert isinstance(PythonRuntime(), Runtime)
    assert isinstance(OctaveRuntime(), Runtime)
