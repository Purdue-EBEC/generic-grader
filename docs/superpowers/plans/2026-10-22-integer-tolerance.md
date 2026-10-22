# Integer Tolerance (#217) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply `rtol`/`atol` to every numeric comparison (integer arrays,
integer scalars, huge ints) so `Options(absolute_tolerance=...)` works on
uint8 image outputs, per issue #217.

**Architecture:** One rule everywhere — `abs(actual - expected) <= atol +
rtol * abs(expected)` — in `deep_compare._walk_number` (scalars) and
`array_diff` (arrays). Float fast path, exact `fractions.Fraction`
fallback beyond float range, `np.array_equal` short-circuit for integer
arrays at exact settings.

**Tech Stack:** Python 3.13, numpy 2.4, pytest, ruff, uv. Spec:
`docs/superpowers/specs/2026-10-21-integer-tolerance-design.md`.

## Global Constraints

- Defaults must not change: `DEFAULT_RTOL = 1e-07`, `DEFAULT_ATOL = 0.0`
  (`src/generic_grader/utils/array_diff.py`); `Options.relative_tolerance
  = 1e-7`, `Options.absolute_tolerance = 0.0`.
- No new dependencies — `fractions` and `operator` are stdlib.
- Run every command from the repo root `/home/john/Work/EBEC/generic-grader`
  using `uv run ...` (never `pip`).
- Pre-commit hook runs on commit. Pre-fix before `git add`:
  `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`.
- Prose in `.md` files wraps at 88 chars; Markdown tables are exempt.
- Commit prefixes: `fix:` (behavior), `test:` (tests only), `docs:` (docs);
  every commit references `(#217)`.
- Branch: `integer-tolerance` off `main` (spec commits `ad959b0`,
  `ad9ff6d` are already on `main`).
- Non-numeric dtypes (bool, datetime, structured, object) and
  `set`/`frozenset` stay exact. Arrays never use `Fraction` (float64 only).

---

### Task 1: deep_compare — unified scalar number rule

**Files:**
- Modify: `src/generic_grader/utils/deep_compare.py`
  (`_num_repr`, `_walk_number`; add module helpers `_is_inf`,
  `_as_fraction`; module docstring)
- Test: `tests/utils/test_deep_compare.py`

**Interfaces:**
- Consumes: `DEFAULT_ATOL`, `DEFAULT_RTOL` (unchanged), `safe_repr` from
  `generic_grader.utils.safe_equal`.
- Produces: `_walk_number` applies the uniform rule to all real numbers
  (numpy integer scalars normalized via `operator.index`). Module-private
  helpers `_is_inf(value) -> bool` and `_as_fraction(value) -> Fraction`.
  `_num_repr` renders `Fraction` values whose `repr` exceeds digit limits.
  Later tasks rely on: `deep_compare(actual, expected, rtol, atol,
  strict_types, max_samples) -> (bool, str)` — signature unchanged.

- [ ] **Step 1: Create the branch**

```bash
cd /home/john/Work/EBEC/generic-grader && git checkout -b integer-tolerance
```

Expected: `Switched to a new branch 'integer-tolerance'`

- [ ] **Step 2: Write the failing tests**

Append to `tests/utils/test_deep_compare.py` (after
`test_tolerance_options_are_honoured`):

```python
def test_uint8_scalars_honour_absolute_tolerance():
    """Issue #217: integer scalars must apply atol (real config uses 1.0)."""
    assert deep_compare(np.uint8(254), np.uint8(255), atol=1.0)[0]
    assert not deep_compare(np.uint8(253), np.uint8(255), atol=1.0)[0]


def test_python_ints_honour_absolute_tolerance():
    assert deep_compare(254, 255, atol=1.0)[0]
    assert not deep_compare(253, 255, atol=1.0)[0]


def test_default_rtol_band_reaches_one_at_1e7():
    # Uniform rule: delta = 1e-7 * 1e7 = 1.0, so diff 1 passes, diff 2 fails.
    assert deep_compare(10_000_001, 10_000_000)[0]
    assert not deep_compare(10_000_002, 10_000_000)[0]


def test_huge_int_within_default_band_passes_via_fraction():
    # Beyond float range the same rule is applied with Fraction arithmetic.
    assert deep_compare(10**5000, 10**5000 + 1)[0]


def test_huge_int_atol_applies_exactly_with_zero_rtol():
    # 0.0 * 10**5000 overflows the float fast path; the Fraction fallback
    # must still apply atol exactly.
    assert deep_compare(10**5000, 10**5000 + 2, rtol=0.0, atol=2.0)[0]
    assert not deep_compare(10**5000, 10**5000 + 3, rtol=0.0, atol=2.0)[0]


def test_single_nan_against_huge_int_fails_without_raising():
    # strict_types=False so dispatch reaches _walk_number (int vs float).
    equal, _details = deep_compare(float("nan"), 10**400, strict_types=False)
    assert equal is False
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/utils/test_deep_compare.py -q -k "uint8 or python_ints or rtol_band or huge_int_within or huge_int_atol or single_nan"`

Expected: 5 fail (`uint8_scalars`, `python_ints`, `rtol_band`,
`huge_int_within`, `huge_int_atol` — integers currently compare exactly);
`single_nan` passes (the current `OverflowError` handler already fails it).
Exit code non-zero.

- [ ] **Step 4: Implement the unified rule**

In `src/generic_grader/utils/deep_compare.py`:

4a. Add imports (top of file, after `import numbers`):

```python
import operator
from fractions import Fraction
```

4b. Replace `_num_repr` (survive `Fraction` whose `repr` exceeds digit
limits):

```python
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
```

4c. Add module helpers after `_safe_eq`:

```python
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
```

4d. Replace the whole body of `_walk_number` (from
`def _walk_number` thr`_walk_number` method — the exact current text is:

```python
    def _walk_number(self, actual, expected, path):
        if isinstance(actual, numbers.Integral) and isinstance(
            expected, numbers.Integral
        ):
            if actual != expected:
                self.fail(
                    path,
                    f"expected={_num_repr(expected)}, actual={_num_repr(actual)}",
                )
            return
        # NaN test on the raw values; must not convert to float (huge ints
        # would raise OverflowError in math.isnan).
        if actual == expected or (actual != actual and expected != expected):  # noqa: PLR0124
            return
        try:
            delta = self.atol + self.rtol * abs(expected)
            diff = abs(actual - expected)
        except OverflowError:
            self.fail(
                path,
                f"expected={_num_repr(expected)}, actual={_num_repr(actual)}",
            )
            return
        infinite = math.isinf(actual) or math.isinf(expected)
        if infinite or not diff <= delta:  # a NaN diff also fails
            self.fail(
                path,
                f"{actual!r} != {expected!r} within {delta!r} ({diff!r} difference)",
            )
```

Replace it
```python
    def _walk_number(self, actual, expected, path):
        # numpy integer scalars wrap on subtraction (np.uint8(254) -
        # np.uint8(255) == 255); Python int arithmetic is exact.
        actual_i = (
            operator.index(actual) if isinstance(actual, numbers.Integral)
            else actual
        )
        expected_i = (
            operator.index(expected) if isinstance(expected, numbers.Integral)
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
            delta = _as_fraction(self.atol) + _as_fraction(
                self.rtol
            ) * _as_fraction(abs(expected_i))
            diff = abs(_as_fraction(actual_i) - _as_fraction(expected_i))

        if not diff <= delta:
            self.fail(
                path,
                f"{_num_repr(actual)} != {_num_repr(expected)}"
                f" within {_num_repr(delta)} ({_num_repr(diff)} difference)",
            )
```

4e. Replace the module docstring's first paragraph (current lines 1-10,
from ``` ``deep_compare`` walks two values together.  Floats compare within ```
through ``` ``==``.  Functions, ```) with:

```python
"""Tolerance-aware recursive comparison of returned values.

``deep_compare`` walks two values together.  Numbers (floats and ints)
compare within ``atol + rtol * abs(expected)`` (the ``np.isclose`` rule);
magnitudes beyond float range use exact ``fractions.Fraction`` arithmetic
so the same rule holds at every size.  numpy arrays are delegated to
:func:`array_compare`, lists/tuples compare element by element, dicts
compare by key, and everything else falls back to ``==``.  Functions,
methods and classes cannot be compared by value, so unless both sides are
the same object they are reported as an autograder misconfiguration.
"""
```

- [ ] **Step 5: Run the full file — expect the two documented flips**

Run: `uv run pytest tests/utils/test_deep_compare.py -q`

Expected: new tests PASS; exactly 2 failures:
- `test_integers_compare_exactly` (`1_000_000_001` vs `1_000_000_000`
  now passes within the rtol band — spec "Behavior changes")
- `test_5000_digit_int_mismatch_reports_without_repr_error`
  (`10**5000` vs `10**5000 + 1` now within band)

- [ ] **Step 6: Update the two flipped tests to encode the new spec**

Replace `test_integers_compare_exactly` (line ~42) with:

```python
def test_small_integers_compare_exactly_at_defaults():
    # The default rtol band (1e-7 * value) stays below 1 under 1e7.
    assert not deep_compare([1_000_000], [1_000_001])[0]


def test_large_integers_compare_exactly_with_zero_tolerances():
    # Exactness for large integers requires tightening the tolerances.
    assert not deep_compare(
        [1_000_000_001], [1_000_000_000], rtol=0.0, atol=0.0
    )[0]
```

Replace `test_5000_digit_int_mismatch_reports_without_repr_error`
(line ~277) with:

```python
def test_5000_digit_int_mismatch_reports_without_repr_error():
    # 10**5000 vs 10**5000 + 1 is within the default band now; compare a
    # mismatch beyond the band so the failure path still renders
    # 5000-digit values without raising ValueError from repr().
    equal, details = deep_compare(10**5000, 2 * 10**5000)
    assert not equal
    # The unified failure message renders both 5000-digit values via
    # _num_repr without raising ValueError from repr().
    assert "!=" in details
    assert "difference)" in details
```

- [ ] **Step 7: Run the full file — verify all pass**

Run: `uv run pytest tests/utils/test_deep_compare.py -q`

Expected: all pass (including unchanged
`test_huge_int_vs_float_does_not_raise_overflow_error`,
`test_nan_equals_nan_and_inf_equals_inf`,
`test_float_outside_tolerance_fails_with_message`). Exit code 0.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/
git add src/generic_grader/utils/deep_compare.py tests/utils/test_deep_compare.py
git commit -m "fix: apply tolerance rule to integer scalars and huge ints (#217)"
```

Expected: ruff clean; commit succeeds (pre-commit hook green because
ruff already ran).

---

### Task 2: array_diff — integer arrays honor tolerance (+ grader e2e)

**Files:**
- Modify: `src/generic_grader/utils/array_diff.py` (add
  `_tolerance_applies`; both guards; `array_compare` docstring)
- Test: `tests/utils/test_array_diff.py`
- Test: `tests/function/test_function_return_values_match_reference.py`

**Interfaces:**
- Consumes: `DEFAULT_ATOL`, `DEFAULT_RTOL` (unchanged).
- Produces: module-private `_tolerance_applies(dtype, rtol, atol) -> bool`
  in `array_diff.py`. `array_compare(actual, expected, rtol, atol,
  max_samples) -> (bool, str)` signature unchanged; `deep_compare` calls it
  unchanged (Task 1 already landed).

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/utils/test_array_diff.py` (after
`test_array_compare_tolerance_outside_atol`):

```python
def test_array_compare_uint8_within_atol():
    """Issue #217: integer arrays honor absolute_tolerance (atol=1.0 is
    the real gaussian_filter config)."""
    a = np.full((4, 4), 254, dtype=np.uint8)
    b = np.full((4, 4), 255, dtype=np.uint8)
    equal, _ = array_compare(a, b, rtol=1e-7, atol=1.0)
    assert equal


def test_array_compare_uint8_outside_atol():
    a = np.full((4, 4), 253, dtype=np.uint8)
    b = np.full((4, 4), 255, dtype=np.uint8)
    equal, details = array_compare(a, b, rtol=1e-7, atol=1.0)
    assert not equal
    assert "at (0, 0)" in details


def test_array_compare_uint8_issue_repro_atol_2():
    # The issue's quoted repro: atol=2.0, diff 1 passes, diff 3 fails.
    b = np.full((4, 4), 255, dtype=np.uint8)
    assert array_compare(np.full((4, 4), 254, np.uint8), b, atol=2.0)[0]
    assert not array_compare(np.full((4, 4), 252, np.uint8), b, atol=2.0)[0]


def test_array_compare_int_default_band_reaches_one_at_1e7():
    a = np.array([10_000_001], dtype=np.int64)
    b = np.array([10_000_000], dtype=np.int64)
    assert array_compare(a, b)[0]
    assert not array_compare(a + 1, b)[0]


def test_array_compare_exact_settings_avoid_float64_promotion():
    # rtol=atol=0 must use np.array_equal: allclose promotes to float64
    # and would call 2**62 + 1 equal to 2**62.
    a = np.array([2**62 + 1], dtype=np.int64)
    b = np.array([2**62], dtype=np.int64)
    equal, details = array_compare(a, b, rtol=0.0, atol=0.0)
    assert not equal
    assert "at (0,)" in details


def test_array_compare_non_numeric_dtypes_stay_exact():
    a = np.array([True, False])
    b = np.array([True, True])
    assert not array_compare(a, b, atol=2.0)[0]
    da = np.array(["2020-01-01", "2020-01-02"], dtype="datetime64[D]")
    db = np.array(["2020-01-01", "2020-01-03"], dtype="datetime64[D]")
    assert not array_compare(da, db, atol=2.0)[0]


def test_array_diff_details_uint8_consistent_with_compare():
    # Issue #207: a failing comparison must report differing indices.
    a = np.full((2, 2), 253, dtype=np.uint8)
    b = np.full((2, 2), 255, dtype=np.uint8)
    equal, details = array_compare(a, b, atol=1.0)
    assert not equal
    assert "at (0, 0)" in details
```

- [ ] **Step 2: Write the failing grader-level cases**

First confirm the anchor exists:

Run: `grep -n "Case: equal np.float64 scalars should pass" tests/function/test_function_return_values_match_reference.py`

Expected: one match (line ~366). In
`tests/function/test_function_return_values_match_reference.py`, insert
the two `cases.append(...)` blocks below immediately before that line:

```python
# Case: absolute_tolerance applies to uint8 image arrays (issue #217)
cases.append(
    {
        "submission": (
            "import numpy as np\n"
            "def test_function():\n"
            "    return np.full((4, 4), 254, dtype=np.uint8)"
        ),
        "reference": (
            "import numpy as np\n"
            "def test_function():\n"
            "    return np.full((4, 4), 255, dtype=np.uint8)"
        ),
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            absolute_tolerance=1.0,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)

# Case: uint8 difference beyond absolute_tolerance still fails (issue #217)
cases.append(
    {
        "submission": (
            "import numpy as np\n"
            "def test_function():\n"
            "    return np.full((4, 4), 253, dtype=np.uint8)"
        ),
        "reference": (
            "import numpy as np\n"
            "def test_function():\n"
            "    return np.full((4, 4), 255, dtype=np.uint8)"
        ),
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            absolute_tolerance=1.0,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    }
)
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `uv run pytest tests/utils/test_array_diff.py -q -k "uint8 or band or promotion or non_numeric or details_uint8"`

Expected: `uint8_within_atol`, `uint8_issue_repro_atol_2`,
`int_default_band` FAIL (integer arrays still exact); guards
(`outside_atol`, `promotion`, `non_numeric`, `details_uint8`) pass.
Exit code non-zero.

Run: `uv run pytest tests/function/test_function_return_values_match_reference.py -q -k "uint8"`

Expected: the "pass" case FAILS (raises `AssertionError`), the "fail"
case passes. Exit code non-zero.

- [ ] **Step 4: Implement `_tolerance_applies` and switch both guards**

In `src/generic_grader/utils/array_diff.py`:

4a. Add after the `DEFAULT_ATOL = 0.0` line:

```python
def _tolerance_applies(dtype, rtol: float, atol: float) -> bool:
    """Whether ``rtol``/``atol`` should decide equality for arrays of *dtype*.

    Integer and floating dtypes compare with ``np.isclose``/``np.allclose``.
    Integer arrays at exact settings (``rtol == 0 and atol == 0``) keep the
    exact ``np.array_equal`` path: ``allclose`` promotes to float64, which
    would call ``2**62 + 1`` equal to ``2**62``.  Other dtypes (bool,
    datetime, structured, object) always compare exactly.
    """
    if np.issubdtype(dtype, np.floating):
        return True
    if np.issubdtype(dtype, np.integer):
        return rtol != 0 or atol != 0
    return False
```

4b. In `array_diff_details`, replace:

```python
    if np.issubdtype(expected.dtype, np.floating):
        diff_mask = ~np.isclose(actual, expected, rtol=rtol, atol=atol)
```

with:

```python
    if _tolerance_applies(expected.dtype, rtol, atol):
        diff_mask = ~np.isclose(actual, expected, rtol=rtol, atol=atol)
```

4c. In `array_compare`, replace:

```python
    # Compare the values of the arrays.
    if np.issubdtype(expected.dtype, np.floating):
        equal = np.allclose(actual, expected, rtol=rtol, atol=atol)
```

with:

```python
    # Compare the values of the arrays.
    if _tolerance_applies(expected.dtype, rtol, atol):
        equal = np.allclose(actual, expected, rtol=rtol, atol=atol)
```

4d. Extend the `array_compare` docstring:

```python
    """Compare two numpy arrays and return (equal, details).

    Integer and floating arrays compare within ``rtol``/``atol``; integer
    arrays at ``rtol == atol == 0`` and all non-numeric dtypes compare
    exactly.  If a numpy comparison function raises, the exception is
    propagated.
    """
```

- [ ] **Step 5: Run both test files — expect one documented flip**

Run: `uv run pytest tests/utils/test_array_diff.py -q && uv run pytest
tests/function/test_function_return_values_match_reference.py -q`

Expected: new tests and both grader cases PASS; exactly 1 failure:
`test_array_compare_propagates_array_equal` (integer arrays at default
tolerances now take the `allclose` path, so the monkeypatched
`array_equal` is never called).

- [ ] **Step 6: Pin the propagates test to the exact path**

In `tests/utils/test_array_diff.py`, replace the body of
`test_array_compare_propagates_array_equal` (line ~193):

```python
def test_array_compare_propagates_array_equal(monkeypatch):
    """Propagates exceptions from np.array_equal on the exact path
    (integer arrays at rtol == atol == 0)."""
    a = np.array([1, 2, 3])
    b = np.array([1, 2, 3])

    # Force array_equal to raise
    monkeypatch.setattr(
        np, *make_mock_function_raise_error("array_equal", RuntimeError)
    )

    with pytest.raises(RuntimeError, match="Your program unexpectedly called"):
        array_compare(a, b, rtol=0.0, atol=0.0)
```

- [ ] **Step 7: Run both test files — verify all pass**

Run: `uv run pytest tests/utils/test_array_diff.py -q && uv run pytest
tests/function/test_function_return_values_match_reference.py -q`

Expected: all pass, exit code 0 (including
`test_array_compare_propagates_allclose`,
`test_array_diff_details_propagates`, `test_array_compare_both_nan`,
`test_array_compare_equal_integer`).

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/
git add src/generic_grader/utils/array_diff.py tests/utils/test_array_diff.py \
  tests/function/test_function_return_values_match_reference.py
git commit -m "fix: apply tolerance to integer arrays and add uint8 e2e cases (#217)"
```

Expected: ruff clean; commit succeeds.

---

### Task 3: Docs — spec dispatch table and module docstrings

**Files:**
- Modify: `docs/superpowers/specs/2026-10-15-collection-comparisons-design.md`
  (dispatch table row, line ~87)
- Modify: `src/generic_grader/utils/array_diff.py` (`array_compare`
  docstring — only if Task 2 Step 4d was not already applied)

**Interfaces:**
- Consumes: behavior landed in Tasks 1-2.
- Produces: documentation consistent with the new uniform rule.

- [ ] **Step 1: Update the old spec's dispatch row**

In `docs/superpowers/specs/2026-10-15-collection-comparisons-design.md`,
replace the table row beginning `| real numbers (`numbers.Real`, not
`bool`) |` with:

```markdown
| real numbers (`numbers.Real`, not `bool`) | The tolerance rule above, computed in pure Python (fast for large lists); integers use the same rule since #217 (exact `Fraction` arithmetic beyond float range); NaN equals NaN |
```

- [ ] **Step 2: Verify docstrings match reality**

Run: `grep -n "np.floating" src/generic_grader/utils/array_diff.py`

Expected: no guard uses `np.floating` alone (only `_tolerance_applies`
mentions dtypes). If `array_compare`'s docstring still lacks the
integer/exact sentence, apply Task 2 Step 4d now.

- [ ] **Step 3: Lint and commit**

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
git add docs/superpowers/specs/2026-10-15-collection-comparisons-design.md \
  src/generic_grader/utils/array_diff.py
git commit -m "docs: record uniform integer tolerance in collection spec (#217)"
```

Expected: ruff clean (no code changed); commit succeeds.

---

### Task 4: Full verification

**Files:**
- None created or modified.

**Interfaces:**
- Consumes: all changes from Tasks 1-3.
- Produces: green suite evidence; branch ready for review/PR.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`

Expected: all tests pass (baseline was 6136 tests, 99% coverage; suite
now has the new cases), exit code 0. If any failure appears, read it —
a stale comment/assertion describing old integer-exactness must be
updated alongside its code (do not weaken the new tests).

- [ ] **Step 2: Run lint and format check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

Expected: `All checks passed!` / no files would be reformatted.

- [ ] **Step 3: Confirm branch state**
3 commits on top of `main` (the Task 1, 2, and 3 commits; the
spec commits `ad959b0`/`ad9ff6d` are already on `main`), clean working
te main..integer-tolerance | cat
&& git status --short`

Expected: 4 commits (spec commits are on `main`, so exactly the Task 1-3
commits plus none from Task 4), clean working tree.

- [ ] **Step 4: Report completion**

Summarize for the user: files changed, test counts, and that the branch
`integer-tolerance` is ready. Do not push or open a PR without asking —
integration choice belongs to the `finishing-a-development-branch` skill.