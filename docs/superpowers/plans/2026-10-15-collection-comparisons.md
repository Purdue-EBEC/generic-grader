# Collection Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare returned values, parsed output values and plot properties with float tolerance at any nesting depth inside lists, tuples, dicts and numpy arrays, terminating on self-referential structures.

**Architecture:** A new `generic_grader.utils.deep_compare.deep_compare(actual, expected, rtol, atol, strict_types, max_samples) -> (equal, details)` walks both values recursively, delegating numpy arrays to the existing `array_compare`. Three graders replace their exact-`==` paths with it and raise `AssertionError(details + hint_message)` as they do today.

**Tech Stack:** Python 3.11+, numpy, pytest, uv, ruff, commitizen.

**Spec:** `docs/superpowers/specs/2026-10-15-collection-comparisons-design.md`

## Global Constraints

- Work on branch `collection-comparisons` (already created from `main`). Run all commands from the repo root `/home/john/Work/EBEC/generic-grader`.
- Use `uv run ...`; never `pip`. No new dependencies.
- Commit messages must be conventional commits (`feat:`, `fix:`, `test:`, `docs:`) so commitizen can generate the changelog. The pre-commit `commitizen` hook enforces this. Do **not** edit `CHANGELOG.md`.
- Before every commit: `uv run ruff check --fix && uv run ruff format` (no path arguments), then `git add`, then `git commit`.
- Tests are plain pytest functions. Do not use the parametrize decorator in new test code (loop inside a test, or build a list of cases, instead).
- Float rule everywhere: `abs(actual - expected) <= atol + rtol * abs(expected)`; NaN equals NaN; two integral values compare exactly. Defaults come from `array_diff.DEFAULT_RTOL` (1e-07) and `DEFAULT_ATOL` (0.0).
- `strict_types=True`: `isinstance(actual, type(expected))` must hold at every level. `strict_types=False`: two real numbers (`numbers.Real`, not `bool`) skip that check; container types must still match.
- `details` is `""` when equal, otherwise it starts with `"\nDetails: "` (same convention as `array_compare`) so callers append their hint message unchanged.
- Exceptions raised by numpy inside `array_compare` must propagate (existing test `test_numpy_comparison_exception_is_propagated` depends on it).
- `instance_attributes_match_reference` and `class_attributes_match_reference` are out of scope (they never compare values).

---

### Task 1: `deep_compare` for numbers, sequences, dicts, arrays and types

**Files:**
- Modify: `src/generic_grader/utils/safe_equal.py` (add public `safe_repr`)
- Create: `src/generic_grader/utils/deep_compare.py`
- Create: `tests/utils/test_deep_compare.py`

**Interfaces:**
- Consumes: `array_compare(actual, expected, rtol, atol, max_samples) -> (bool, str)` and `DEFAULT_RTOL`, `DEFAULT_ATOL` from `generic_grader.utils.array_diff`.
- Produces:
  - `generic_grader.utils.safe_equal.safe_repr(value) -> str` (truncated `reprlib` repr).
  - `generic_grader.utils.deep_compare.deep_compare(actual, expected, rtol=DEFAULT_RTOL, atol=DEFAULT_ATOL, strict_types=True, max_samples=5) -> tuple[bool, str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/utils/test_deep_compare.py`:

```python
import numpy as np
import pytest

from generic_grader.utils.deep_compare import deep_compare


def test_reported_gradescope_tuple_passes():
    actual = (31.999999999999996, 91.84322033898306, 236.0)
    expected = (32.00000000000001, 91.84322033898306, 236.0)
    assert deep_compare(actual, expected) == (True, "")


def test_equal_values_return_empty_details():
    assert deep_compare([1, 2.5, "a", (None, True)], [1, 2.5, "a", (None, True)]) == (
        True,
        "",
    )


def test_float_outside_tolerance_fails_with_message():
    equal, details = deep_compare([1.0, 2.1], [1.0, 2.0])
    assert not equal
    assert details.startswith("\nDetails: at [1]:")
    assert "2.1 != 2.0 within" in details
    assert "difference)" in details


def test_tolerance_options_are_honoured():
    assert deep_compare([3.05], [3.0], rtol=0.1)[0]
    assert deep_compare([3.5], [3.0], rtol=0.0, atol=1.0)[0]
    assert not deep_compare([3.00000001], [3.0], rtol=1e-10)[0]


def test_nan_equals_nan_and_inf_equals_inf():
    assert deep_compare((float("nan"), float("inf")), (float("nan"), float("inf")))[0]
    assert not deep_compare((float("nan"),), (1.0,))[0]
    assert not deep_compare((float("-inf"),), (float("inf"),))[0]
    assert not deep_compare((1.0,), (float("inf"),))[0]
    assert not deep_compare((float("inf"),), (1.0,))[0]


def test_integers_compare_exactly():
    assert not deep_compare([1_000_000_001], [1_000_000_000])[0]


def test_nested_path_is_reported():
    actual = {"a": [1, (2.0, 3.5)]}
    expected = {"a": [1, (2.0, 3.0)]}
    equal, details = deep_compare(actual, expected)
    assert not equal
    assert "at ['a'][1][1]:" in details


def test_top_level_failure_names_top_level():
    equal, details = deep_compare("abc", "abd")
    assert not equal
    assert "at top level:" in details
    assert "expected='abd', actual='abc'" in details


def test_sequence_length_mismatch():
    equal, details = deep_compare([1, 2], [1, 2, 3])
    assert not equal
    assert "expected length 3, got 2" in details


def test_dict_key_order_is_ignored():
    assert deep_compare({"a": 1.0, "b": 2.0}, {"b": 2.0, "a": 1.0})[0]


def test_dict_missing_and_extra_keys():
    equal, details = deep_compare({"a": 1, "c": 3}, {"a": 1, "b": 2})
    assert not equal
    assert "missing keys ['b']" in details
    assert "extra keys ['c']" in details


def test_dict_value_tolerance():
    assert deep_compare({"b": 2.00000000001}, {"b": 2.0})[0]


def test_sets_use_exact_equality():
    assert deep_compare({1, 2}, {2, 1})[0]
    assert not deep_compare({1, 2}, {1, 3})[0]


def test_array_inside_collections_uses_tolerance():
    actual = {"a": (np.array([1.0, 2.0 + 1e-12]),)}
    expected = {"a": (np.array([1.0, 2.0]),)}
    assert deep_compare(actual, expected)[0]


def test_array_difference_reports_path():
    actual = [np.array([1, 2, 4])]
    expected = [np.array([1, 2, 3])]
    equal, details = deep_compare(actual, expected)
    assert not equal
    assert "at [0]:" in details
    assert "at (2,)" in details
    assert "actual=" in details


def test_array_shape_difference_reports_shape():
    equal, details = deep_compare(np.zeros((2, 2)), np.zeros((4,)))
    assert not equal
    assert "shapes differ" in details


def test_numpy_exceptions_propagate(monkeypatch):
    def raise_error(*args, **kwargs):
        raise RuntimeError("comparison failed")

    monkeypatch.setattr(np, "allclose", raise_error)
    with pytest.raises(RuntimeError):
        deep_compare(np.array([1.0]), np.array([1.0]))


def test_strict_types_reject_container_and_number_mismatches():
    for actual, expected, text in (
        ((1, 2), [1, 2], "expected type list, got tuple"),
        ([1], [1.0], "expected type float, got int"),
        (3.0, np.float64(3.0), "expected type float64, got float"),
    ):
        equal, details = deep_compare(actual, expected)
        assert not equal
        assert text in details


def test_subclass_of_expected_type_passes_strict_check():
    assert deep_compare(np.float64(3.0), 3.0)[0]


def test_relaxed_types_accept_int_for_float_but_not_container_swap():
    assert deep_compare(3, 3.0, strict_types=False)[0]
    assert deep_compare([3, 4.0], [3.0, 4], strict_types=False)[0]
    assert not deep_compare((3,), [3], strict_types=False)[0]
    assert not deep_compare("3", 3.0, strict_types=False)[0]


def test_bool_is_not_a_real_number():
    assert not deep_compare(1, True)[0]
    assert deep_compare(True, True)[0]


def test_max_samples_limits_reported_failures():
    equal, details = deep_compare(
        list(range(10)), [x + 100 for x in range(10)], max_samples=3
    )
    assert not equal
    assert details.count("at [") == 3


def test_object_whose_equality_raises_is_a_mismatch():
    class Boom:
        def __eq__(self, other):
            raise RuntimeError("boom")

    equal, details = deep_compare([Boom()], [Boom()])
    assert not equal
    assert "at [0]:" in details
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/utils/test_deep_compare.py -q --no-cov`
Expected: collection error, `ModuleNotFoundError: No module named 'generic_grader.utils.deep_compare'`.

- [ ] **Step 3: Add `safe_repr` to `safe_equal.py`**

In `src/generic_grader/utils/safe_equal.py`, directly after the `_safe_repr.maxset = 20` line, add:

```python
def safe_repr(value):
    """Return a truncated ``repr`` of *value* that is safe for large data."""
    return _safe_repr.repr(value)
```

- [ ] **Step 4: Write the implementation**

Create `src/generic_grader/utils/deep_compare.py`:

```python
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
        if actual == expected or (actual != actual and expected != expected):
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
        if len(actual) != len(expected):
            self.fail(path, f"expected length {len(expected)}, got {len(actual)}")
            return
        for i, (a, e) in enumerate(zip(actual, expected)):
            self.walk(a, e, f"{path}[{i}]")

    def _walk_dict(self, actual, expected, path):
        missing = [k for k in expected if k not in actual]
        extra = [k for k in actual if k not in expected]
        if missing or extra:
            self.fail(
                path,
                f"missing keys {safe_repr(missing)}, extra keys {safe_repr(extra)}",
            )
            return
        for key, e in expected.items():
            self.walk(actual[key], e, f"{path}[{safe_repr(key)}]")


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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run ruff check --fix && uv run ruff format && uv run pytest tests/utils/test_deep_compare.py -q --no-cov`
Expected: all tests pass. If `test_array_difference_reports_path` fails, print `details`; it should contain `at [0]: at (2,): expected=..., actual=...` (the exact scalar repr depends on the numpy version).

- [ ] **Step 6: Commit**

```bash
git add src/generic_grader/utils/deep_compare.py src/generic_grader/utils/safe_equal.py tests/utils/test_deep_compare.py
git commit -m "feat: add tolerance-aware recursive deep_compare utility"
```

---

### Task 2: Cycle safety in `deep_compare`

**Files:**
- Modify: `src/generic_grader/utils/deep_compare.py` (`_Comparison.__init__`, `_walk_sequence`, `_walk_dict`)
- Modify: `tests/utils/test_deep_compare.py` (append tests)

**Interfaces:**
- Consumes: `deep_compare` and `_Comparison` from Task 1.
- Produces: unchanged public signature; `deep_compare` now terminates on any finite object graph, including lists and dicts that contain themselves.

- [ ] **Step 1: Write the failing tests**

Append to `tests/utils/test_deep_compare.py`:

```python
def make_self_list(first=1):
    value = [first]
    value.append(value)
    return value


def make_self_dict(first=1):
    value = {"x": first}
    value["self"] = value
    return value


def test_equal_self_containing_lists_pass():
    assert deep_compare(make_self_list(), make_self_list()) == (True, "")


def test_different_self_containing_lists_fail():
    equal, details = deep_compare(make_self_list(1), make_self_list(2))
    assert not equal
    assert "at [0]:" in details


def test_equal_self_containing_dicts_pass():
    assert deep_compare(make_self_dict(), make_self_dict()) == (True, "")


def test_different_self_containing_dicts_fail():
    equal, details = deep_compare(make_self_dict(1.0), make_self_dict(2.0))
    assert not equal
    assert "at ['x']:" in details


def test_self_containing_student_list_against_finite_reference_fails():
    equal, details = deep_compare(make_self_list(), [1, [1, []]])
    assert not equal


def test_finite_student_list_against_self_containing_reference_fails():
    equal, details = deep_compare([1, [1, []]], make_self_list())
    assert not equal


def test_mutually_recursive_structures_terminate():
    a, b = [], []
    a.append(b)
    b.append(a)
    c, d = [], []
    c.append(d)
    d.append(c)
    assert deep_compare(a, c) == (True, "")


def test_shared_non_cyclic_substructure_is_compared_each_time():
    shared_actual = [1.0]
    shared_expected = [2.0]
    equal, details = deep_compare(
        [shared_actual, shared_actual], [shared_expected, shared_expected]
    )
    assert not equal
    assert "at [0][0]:" in details
    assert "at [1][0]:" in details
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/utils/test_deep_compare.py -q --no-cov -k "self or mutually or shared"`
Expected: the cyclic tests fail with `RecursionError`; the shared-substructure test already passes (it guards against over-eager skipping once the fix lands).

- [ ] **Step 3: Add the in-progress set and guard both container walkers**

In `src/generic_grader/utils/deep_compare.py`, in `_Comparison.__init__` replace

```python
        self.failures = []
```

with

```python
        self.failures = []
        self.in_progress = set()  # (id(actual), id(expected)) pairs being walked
```

Replace the whole `_walk_sequence` method with:

```python
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
```

Replace the whole `_walk_dict` method with:

```python
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
```

- [ ] **Step 4: Run all `deep_compare` tests**

Run: `uv run ruff check --fix && uv run ruff format && uv run pytest tests/utils/test_deep_compare.py -q --no-cov`
Expected: all tests pass, none raise `RecursionError`.

- [ ] **Step 5: Commit**

```bash
git add src/generic_grader/utils/deep_compare.py tests/utils/test_deep_compare.py
git commit -m "fix: terminate deep_compare on self-referential lists and dicts"
```

---

### Task 3: Use `deep_compare` in `function_return_values_match_reference`

**Files:**
- Modify: `src/generic_grader/function/function_return_values_match_reference.py`
- Modify: `tests/function/test_function_return_values_match_reference.py` (insert before the line `@pytest.fixture(params=cases)`)

**Interfaces:**
- Consumes: `deep_compare(actual, expected, rtol, atol)` from Tasks 1-2 (default `strict_types=True`).
- Produces: nothing new; the grader's public behavior changes as listed in the spec ("Behavior changes").

- [ ] **Step 1: Write the failing tests**

In `tests/function/test_function_return_values_match_reference.py`, immediately above `@pytest.fixture(params=cases)`, insert:

```python
# Cases: collections containing floats or numpy arrays (ported from the
# better_collection_comparisons branch, plus the reported Gradescope failure).

_NP = "import numpy as np\n"
_DOC = (
    "Check that the value(s) returned from your `submission.test_function`"
    " function when called as `test_function()` match the reference value(s)."
)


def _collection_case(
    sub_return, ref_return, result="pass", message="", imports="", **kw
):
    """Build a case whose functions return the given expressions."""
    case = {
        "submission": f"{imports}def test_function():\n    return {sub_return}",
        "reference": f"{imports}def test_function():\n    return {ref_return}",
        "result": result,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            **kw,
        ),
        "doc_func_test_string": _DOC,
    }
    if result != "pass":
        case["message"] = message
    return case


_VALUE_MSG = "Double check the value(s) returned"

cases.extend(
    [
        _collection_case(  # Reported failure: tuple of floats 1e-14 apart
            "(31.999999999999996, 91.84322033898306, 236.0)",
            "(32.00000000000001, 91.84322033898306, 236.0)",
        ),
        _collection_case(  # Tuple of equal numpy arrays
            "(np.array([1,2,3]), np.array([4,5,6]))",
            "(np.array([1,2,3]), np.array([4,5,6]))",
            imports=_NP,
        ),
        _collection_case(  # Tuple of arrays, first differs
            "(np.array([1,2,4]), np.array([4,5,6]))",
            "(np.array([1,2,3]), np.array([4,5,6]))",
            AssertionError,
            "at [0]:",
            imports=_NP,
        ),
        _collection_case(  # List of equal numpy arrays
            "[np.array([1,2,3]), np.array([4,5,6])]",
            "[np.array([1,2,3]), np.array([4,5,6])]",
            imports=_NP,
        ),
        _collection_case(  # Mixed types
            "[1, 2.5, np.array([1,2,3]), 'hello']",
            "[1, 2.5, np.array([1,2,3]), 'hello']",
            imports=_NP,
        ),
        _collection_case(  # List of nearly equal floats
            "[1.0, 2.0000000001, 3.0]", "[1.0, 2.0, 3.0]"
        ),
        _collection_case(  # Dict of equal arrays
            "{'a': np.array([1,2,3]), 'b': np.array([4,5,6])}",
            "{'a': np.array([1,2,3]), 'b': np.array([4,5,6])}",
            imports=_NP,
        ),
        _collection_case(  # Dict of arrays, one differs
            "{'a': np.array([1,2,4]), 'b': np.array([4,5,6])}",
            "{'a': np.array([1,2,3]), 'b': np.array([4,5,6])}",
            AssertionError,
            "at ['a']:",
            imports=_NP,
        ),
        _collection_case(  # Nested lists of equal arrays
            "[[1, 2], [np.array([1,2,3]), np.array([4,5,6])]]",
            "[[1, 2], [np.array([1,2,3]), np.array([4,5,6])]]",
            imports=_NP,
        ),
        _collection_case(  # Nested lists, nested array differs
            "[[1, 2], [np.array([1,2,4]), np.array([4,5,6])]]",
            "[[1, 2], [np.array([1,2,3]), np.array([4,5,6])]]",
            AssertionError,
            "at [1][0]:",
            imports=_NP,
        ),
        _collection_case(  # Tuple of nearly equal floats
            "(1.0, 2.0000000001, 3.0)", "(1.0, 2.0, 3.0)"
        ),
        _collection_case(  # Dict of nearly equal floats
            "{'a': 1.0, 'b': 2.0000000001, 'c': 3.0}", "{'a': 1.0, 'b': 2.0, 'c': 3.0}"
        ),
        _collection_case(  # Float outside tolerance inside a tuple
            "(1.0, 2.1)", "(1.0, 2.0)", AssertionError, _VALUE_MSG
        ),
        _collection_case(  # Tight rtol rejects a nested float
            "(3.00000001,)",
            "(3.0,)",
            AssertionError,
            "difference)",
            relative_tolerance=1e-10,
        ),
        _collection_case(  # Nested int where float expected
            "[1]", "[1.0]", AssertionError, "expected type float, got int"
        ),
        _collection_case(  # Tuple where list expected
            "[(1, 2)]", "[[1, 2]]", AssertionError, "expected type list, got tuple"
        ),
    ]
)

cases.extend(
    [
        _collection_case(  # Self-containing list equals an equal one
            "(lambda a: (a.append(a), a)[1])([1])",
            "(lambda a: (a.append(a), a)[1])([1])",
        ),
        _collection_case(  # Self-containing list vs different self-containing list
            "(lambda a: (a.append(a), a)[1])([1])",
            "(lambda a: (a.append(a), a)[1])([2])",
            AssertionError,
            "at [0]:",
        ),
        _collection_case(  # Self-containing dict vs different self-containing dict
            "(lambda d: (d.update(me=d), d)[1])({'x': 1})",
            "(lambda d: (d.update(me=d), d)[1])({'x': 2})",
            AssertionError,
            "at ['x']:",
        ),
    ]
)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/function/test_function_return_values_match_reference.py -q --no-cov`
Expected: the new "pass" cases for floats in tuples/lists/dicts and the cycle cases fail (exact `==` mismatch or `RecursionError`); the old cases still pass.

- [ ] **Step 3: Replace the comparison logic**

In `src/generic_grader/function/function_return_values_match_reference.py`:

Replace the imports

```python
import numpy as np
from parameterized import parameterized

from generic_grader.utils.array_diff import array_compare
from generic_grader.utils.decorators import weighted
```

with

```python
from parameterized import parameterized

from generic_grader.utils.deep_compare import deep_compare
from generic_grader.utils.decorators import weighted
```

and delete the line `from generic_grader.utils.safe_equal import safe_assert_equal`.

Replace everything from `if isinstance(expected, np.ndarray):` through the final `safe_assert_equal(self, actual, expected, msg=value_msg)` (just above `self.set_score(self, o.weight)  # Full credit`) with:

```python
equal, details = deep_compare(
    actual,
    expected,
    rtol=o.relative_tolerance,
    atol=o.absolute_tolerance,
)
if not equal:
    raise AssertionError(details + value_msg)
```

Keep `self.assertIsInstance(actual, expected_type, msg=type_msg)` above it.

- [ ] **Step 4: Run the grader tests**

Run: `uv run ruff check --fix && uv run ruff format && uv run pytest tests/function/test_function_return_values_match_reference.py -q --no-cov`
Expected: all pass, including the existing `np.float64` `"difference)"` cases and `test_numpy_comparison_exception_is_propagated`.

- [ ] **Step 5: Commit**

```bash
git add src/generic_grader/function/function_return_values_match_reference.py tests/function/test_function_return_values_match_reference.py
git commit -m "feat: compare returned collections with float tolerance

Return values that are tuples, lists or dicts of floats or numpy arrays
now compare within rtol/atol at any depth instead of by exact equality.
Bare float returns also use rtol/atol instead of assertAlmostEqual's
7 decimal places, and nested elements are type-checked strictly."
```

---

### Task 4: Use `deep_compare` in `output_values_match_reference` and `plot_prop_matches_reference`

**Files:**
- Modify: `src/generic_grader/output/output_values_match_reference.py`
- Modify: `src/generic_grader/image/plot_prop_matches_reference.py`
- Modify: `tests/output/test_output_values_match_reference.py`
- Modify: `tests/image/test_plot_prop_matches_reference.py`

**Interfaces:**
- Consumes: `deep_compare(actual, expected, rtol, atol, strict_types=False)`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**

In `tests/output/test_output_values_match_reference.py`, immediately above `@pytest.fixture(params=cases)`, insert:

```python
cases.append(
    {  # Printed values within tolerance of the reference
        "submission": "def main():\n    print('1.00000000001, 2')",
        "reference": "def main():\n    print('1.0, 2')",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the values on output line 1 from your `main` function"
            " when called as `main()` match the reference values."
        ),
    }
)
cases.append(
    {  # Tight tolerance rejects the same values
        "submission": "def main():\n    print('1.00000000001, 2')",
        "reference": "def main():\n    print('1.0, 2')",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            relative_tolerance=1e-14,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": (
            "Check that the values on output line 1 from your `main` function"
            " when called as `main()` match the reference values."
        ),
    }
)
```

In `tests/image/test_plot_prop_matches_reference.py`, immediately above the line `passing_cases = [`, insert:

```python
plot_limits_text = plot_one_text + "    ax.set_xlim(0, 10)\n"
plot_limits_close_text = plot_one_text + "    ax.set_xlim(0, 10.000000001)\n"
plot_limits_far_text = plot_one_text + "    ax.set_xlim(0, 11)\n"
```

then add to the `passing_cases` list (before its closing `]`):

```python
(
    {  # Tuple of axis limits within tolerance
        "submission": plot_limits_close_text,
        "reference": plot_limits_text,
        "options": Options(
            prop="x limits", weight=1, ref_module="ref", sub_module="sub"
        ),
    },
)
```

and to the `failing_cases` list (before its closing `]`):

```python
(
    {  # Tuple of axis limits outside tolerance
        "submission": plot_limits_far_text,
        "reference": plot_limits_text,
        "options": Options(
            prop="x limits", weight=1, ref_module="ref", sub_module="sub"
        ),
        "msg": "Double check the x limits\n  in the plot produced by your `main` function when called as\n  `main()`.",
    },
)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/output/test_output_values_match_reference.py tests/image/test_plot_prop_matches_reference.py -q --no-cov`
Expected: the two new passing cases (output values within tolerance, x limits within tolerance) fail with exact-`==` mismatches. The two new failing cases already pass.

- [ ] **Step 3: Switch `output_values_match_reference`**

In `src/generic_grader/output/output_values_match_reference.py`, replace

```python
from generic_grader.utils.decorators import weighted
```

with

```python
from generic_grader.utils.decorators import weighted
from generic_grader.utils.deep_compare import deep_compare
```

delete `from generic_grader.utils.safe_equal import safe_assert_equal`, and replace the line

```python
            safe_assert_equal(self, actual, expected, msg=message)
```

with

```python
            equal, details = deep_compare(
                actual,
                expected,
                rtol=o.relative_tolerance,
                atol=o.absolute_tolerance,
                strict_types=False,
            )
            if not equal:
                raise AssertionError(details + message)
```

- [ ] **Step 4: Switch `plot_prop_matches_reference`**

In `src/generic_grader/image/plot_prop_matches_reference.py`, add

```python
from generic_grader.utils.deep_compare import deep_compare
```

after `from generic_grader.utils.decorators import weighted`, delete the `safe_assert_equal` import, and replace the final branch

```python
            else:
                safe_assert_equal(self, actual, expected, msg=message)
```

with

```python
            else:
                equal, details = deep_compare(
                    actual,
                    expected,
                    rtol=o.relative_tolerance,
                    atol=o.absolute_tolerance,
                    strict_types=False,
                )
                if not equal:
                    raise AssertionError(details + message)
```

- [ ] **Step 5: Run the tests**

Run: `uv run ruff check --fix && uv run ruff format && uv run pytest tests/output tests/image -q --no-cov`
Expected: all pass. If an existing plot "x data" failing case now reports a different message prefix, the asserted substring (`Double check the x data ...`) is part of `message` and still present.

- [ ] **Step 6: Commit**

```bash
git add src/generic_grader/output/output_values_match_reference.py src/generic_grader/image/plot_prop_matches_reference.py tests/output/test_output_values_match_reference.py tests/image/test_plot_prop_matches_reference.py
git commit -m "feat: apply float tolerance to output values and plot properties

output_values_match_reference and plot_prop_matches_reference now use
deep_compare with relative_tolerance and absolute_tolerance, so parsed
numbers and tuples of axis limits no longer need to match exactly."
```

---

### Task 5: Full verification

**Files:** none modified unless a failure is found.

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass. Investigate and fix any failure outside the files above before continuing (for example another test that relied on exact-`==` behavior for return values).

- [ ] **Step 2: Reproduce the original report end-to-end**

Run:

```bash
mkdir -p .tmp/repro && cat > .tmp/repro/check.py <<'PY'
from generic_grader.utils.deep_compare import deep_compare

print(
    deep_compare(
        (31.999999999999996, 91.84322033898306, 236.0),
        (32.00000000000001, 91.84322033898306, 236.0),
    )
)
PY
uv run python .tmp/repro/check.py; rm -rf .tmp/repro
```

Expected: `(True, '')`.

- [ ] **Step 3: Check commit messages and tree state**

Run: `uv run cz check --rev-range main..HEAD && git status --short && git --no-pager log --oneline main..HEAD | cat`
Expected: `cz check` reports all commits valid, the tree is clean, and the log shows the two spec commits plus the plan commit and the four implementation commits.

- [ ] **Step 4: Note the downstream follow-up (no code change here)**

The ENGR 13300 content repo pins a `generic-grader` revision. After this branch merges and a release is cut, bump that pin and rebuild the `tp1.team_1_a` grader to confirm the `rgb_to_hsv(236, 215, 151)` case passes on Gradescope.
