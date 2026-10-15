"""Tolerance-aware recursive comparison of returned values.

``deep_compare`` walks two values together.  Floats compare within
``atol + rtol * abs(expected)`` (the ``np.isclose`` rule), numpy arrays are
delegated to :func:`array_compare`, lists/tuples compare element by element,
dicts compare by key, and everything else falls back to ``==``.
"""

import math
import numbers

import numpy as np

from generic_grader.utils.array_diff import DEFAULT_ATOL, DEFAULT_RTOL, array_compare
from generic_grader.utils.safe_equal import safe_repr

ROOT = "top level"


def _is_real(value):
    """Return True for real numbers, excluding bool."""
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _safe_eq(actual, expected):
    """Return ``actual == expected``; a raising or ambiguous ``==`` is False."""
    try:
        return bool(actual == expected)
    except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
        return False


class _Comparison:
    """State for one call to :func:`deep_compare`."""

    def __init__(self, rtol, atol, strict_types, max_samples):
        self.rtol = rtol
        self.atol = atol
        self.strict_types = strict_types
        self.max_samples = max_samples
        self.failures = []
        self.in_progress = set()  # (id(actual), id(expected)) pairs being walked

    def fail(self, path, text):
        self.failures.append(f"at {path or ROOT}: {text}")

    def walk(self, actual, expected, path=""):
        if len(self.failures) >= self.max_samples:
            return
        if not self._types_match(actual, expected):
            self.fail(
                path,
                f"expected type {type(expected).__name__}, got {type(actual).__name__}",
            )
        elif isinstance(expected, np.ndarray):
            equal, details = array_compare(
                actual,
                expected,
                rtol=self.rtol,
                atol=self.atol,
                max_samples=self.max_samples,
            )
            if not equal:
                self.fail(path, details.removeprefix("\nDetails: ").strip())
        elif _is_real(expected) and _is_real(actual):
            self._walk_number(actual, expected, path)
        elif isinstance(expected, (list, tuple)):
            self._walk_sequence(actual, expected, path)
        elif isinstance(expected, dict):
            self._walk_dict(actual, expected, path)
        elif not _safe_eq(actual, expected):
            self.fail(
                path, f"expected={safe_repr(expected)}, actual={safe_repr(actual)}"
            )

    def _types_match(self, actual, expected):
        if not self.strict_types and _is_real(actual) and _is_real(expected):
            return True
        try:
            return isinstance(actual, type(expected))
        except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
            return False

    def _walk_number(self, actual, expected, path):
        if isinstance(actual, numbers.Integral) and isinstance(
            expected, numbers.Integral
        ):
            if actual != expected:
                self.fail(path, f"expected={expected!r}, actual={actual!r}")
            return
        if actual == expected or (math.isnan(actual) and math.isnan(expected)):
            return
        delta = self.atol + self.rtol * abs(expected)
        diff = abs(actual - expected)
        infinite = math.isinf(actual) or math.isinf(expected)
        if infinite or not diff <= delta:  # a NaN diff also fails
            self.fail(
                path,
                f"{actual!r} != {expected!r} within {delta!r} ({diff!r} difference)",
            )

    def _walk_sequence(self, actual, expected, path):
        key = (id(actual), id(expected))
        if key in self.in_progress:
            return  # Cycle: assume equal; any real difference is found elsewhere.
        if len(actual) != len(expected):
            self.fail(path, f"expected length {len(expected)}, got {len(actual)}")
            return
        self.in_progress.add(key)
        try:
            for i, (a, e) in enumerate(zip(actual, expected)):
                self.walk(a, e, f"{path}[{i}]")
        finally:
            self.in_progress.discard(key)

    def _walk_dict(self, actual, expected, path):
        key = (id(actual), id(expected))
        if key in self.in_progress:
            return  # Cycle: assume equal; any real difference is found elsewhere.
        missing = [k for k in expected if k not in actual]
        extra = [k for k in actual if k not in expected]
        if missing or extra:
            self.fail(
                path,
                f"missing keys {safe_repr(missing)}, extra keys {safe_repr(extra)}",
            )
            return
        self.in_progress.add(key)
        try:
            for name, e in expected.items():
                self.walk(actual[name], e, f"{path}[{safe_repr(name)}]")
        finally:
            self.in_progress.discard(key)


def deep_compare(
    actual,
    expected,
    rtol: float = DEFAULT_RTOL,
    atol: float = DEFAULT_ATOL,
    strict_types: bool = True,
    max_samples: int = 5,
):
    """Compare two values recursively and return ``(equal, details)``.

    ``details`` is empty when the values are equal; otherwise it starts with
    ``"\\nDetails: "`` and lists up to ``max_samples`` failures, each naming
    the path of the failing element.
    """
    comparison = _Comparison(rtol, atol, strict_types, max_samples)
    comparison.walk(actual, expected)
    if not comparison.failures:
        return True, ""
    return False, "\nDetails: " + "\n".join(comparison.failures)
