"""Tolerance-aware recursive comparison of returned values.

``deep_compare`` walks two values together.  Numbers (floats and ints)
compare within ``atol + rtol * abs(expected)`` (the ``np.isclose`` rule);
magnitudes beyond float range use exact ``fractions.Fraction`` arithmetic
so the same rule holds at every size.  numpy arrays are delegated to
:func:`array_compare`, lists/tuples compare element by element, dicts
compare by key, and everything else falls back to ``==``.  Functions,
methods and classes cannot be compared by value, so unless both sides are the
same object they are reported as an autograder misconfiguration.
"""

import functools
import math
import numbers
import operator
import types
from fractions import Fraction

import numpy as np

from generic_grader.utils.array_diff import DEFAULT_ATOL, DEFAULT_RTOL, array_compare
from generic_grader.utils.safe_equal import make_diff, safe_repr

ROOT = "top level"

_CALLABLE_TYPES = (
    types.FunctionType,
    types.BuiltinFunctionType,
    types.MethodType,
    functools.partial,
    type,
)


def _callable_name(value):
    """Return ``module.qualname`` for *value*, or its repr if that fails."""
    try:
        return f"{value.__module__}.{value.__qualname__}"
    except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
        return safe_repr(value)


def _num_repr(value):
    """``safe_repr`` that also survives values repr() refuses to render."""
    try:
        return safe_repr(value)
    except ValueError:
        # repr() refuses ints over sys.int_max_str_digits and Fractions
        # built from them; describe the magnitude instead.
        magnitude = getattr(value, "numerator", value)
        try:
            return f"<{type(value).__name__} with {magnitude.bit_length()} bits>"
        except (AttributeError, ValueError):
            return f"<{type(value).__name__}>"


def _is_real(value):
    """Return True for real numbers, excluding bool."""
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _safe_eq(actual, expected):
    """Return ``actual == expected``; a raising or ambiguous ``==`` is False."""
    try:
        return bool(actual == expected)
    except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
        return False


def _is_inf(value):
    """True for +/-infinity; integers are never infinite (and math.isinf
    raises OverflowError on ints beyond float range)."""
    if isinstance(value, numbers.Integral):
        return False
    return math.isinf(value)


def _as_fraction(value):
    """Exact ``Fraction`` for *value*; ints skip the float conversion."""
    if isinstance(value, numbers.Integral):
        return Fraction(operator.index(value))
    return Fraction(float(value))


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
        elif isinstance(expected, _CALLABLE_TYPES):
            if actual is not expected:
                self.fail(
                    path,
                    "callables cannot be compared by value"
                    f" (expected {_callable_name(expected)},"
                    f" actual {_callable_name(actual)})."
                    "  This is a bug in the autograder; please notify your"
                    " instructor.  Test authors: compare the results of calling"
                    " them instead, or use the class_* graders for classes.",
                )
        elif not _safe_eq(actual, expected):
            text = f"expected={safe_repr(expected)}, actual={safe_repr(actual)}"
            if isinstance(actual, str) and isinstance(expected, str):
                diff = make_diff(actual, expected)
                if diff:
                    text += "\n" + diff.rstrip("\n")
            self.fail(path, text)

    def _types_match(self, actual, expected):
        if not self.strict_types and _is_real(actual) and _is_real(expected):
            return True
        try:
            return isinstance(actual, type(expected))
        except Exception:  # noqa: BLE001 - submitted objects can be arbitrary
            return False

    def _walk_number(self, actual, expected, path):
        # numpy integer scalars wrap on subtraction (np.uint8(254) -
        # np.uint8(255) == 255); Python int arithmetic is exact.
        actual_i = (
            operator.index(actual) if isinstance(actual, numbers.Integral) else actual
        )
        expected_i = (
            operator.index(expected)
            if isinstance(expected, numbers.Integral)
            else expected
        )

        # NaN test on the raw values; must not convert to float (huge ints
        # would raise OverflowError in math.isnan).  NaN equals NaN.
        if actual == expected or (actual != actual and expected != expected):  # noqa: PLR0124
            return
        if actual != actual or expected != expected:  # noqa: PLR0124
            # One-sided NaN is never within tolerance; fail before the
            # arithmetic below (Fraction(nan) would raise ValueError).
            self.fail(
                path,
                f"expected={_num_repr(expected)}, actual={_num_repr(actual)}",
            )
            return
        if _is_inf(actual) or _is_inf(expected):
            # Equal infinities returned above; check before the arithmetic
            # (a huge int against inf overflows).
            self.fail(
                path,
                f"{_num_repr(actual)} != {_num_repr(expected)} (infinite value)",
            )
            return

        try:
            delta = self.atol + self.rtol * abs(expected_i)
            diff = abs(actual_i - expected_i)
        except OverflowError:
            # Magnitudes beyond float range: apply the same rule exactly.
            delta = _as_fraction(self.atol) + _as_fraction(self.rtol) * _as_fraction(
                abs(expected_i)
            )
            diff = abs(_as_fraction(actual_i) - _as_fraction(expected_i))

        if not diff <= delta:
            self.fail(
                path,
                f"{_num_repr(actual)} != {_num_repr(expected)}"
                f" within {_num_repr(delta)} ({_num_repr(diff)} difference)",
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
