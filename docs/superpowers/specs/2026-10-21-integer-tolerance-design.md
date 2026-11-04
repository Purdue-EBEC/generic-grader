# Design: uniform tolerance for integer comparisons

Date: 2026-10-21
Status: Approved (pending spec review)

## Problem

Issue #217: `Options(absolute_tolerance=...)` on a
`function_return_values_match_reference` test whose cases are uint8 images
still fails on a one-gray-level difference. The issue quotes a repro with
`absolute_tolerance=2.0`; the real GTSRB `gaussian_filter` config sets
`absolute_tolerance=1.0` (diff of 1 passes at atol=1 since
`1 <= 1 + 1e-7 * 255`; diff of 2 fails).

```text
Details: at top level: at (3, 3): expected=np.uint8(255), actual=np.uint8(254)
```

Two guards restrict tolerance to floating-point dtypes:

- `array_diff.py`: `array_compare` and `array_diff_details` only use
  `np.allclose`/`np.isclose` when `np.issubdtype(expected.dtype,
  np.floating)`; integer arrays fall through to exact
  `np.array_equal`/`!=`.
- `deep_compare._walk_number`: two `numbers.Integral` scalars (which
  includes `np.uint8`) are compared with plain `!=`.

The options plumbing is fine — the tolerance is dropped at the comparison
layer.

## Goals

- One rule for every numeric comparison:
  `abs(actual - expected) <= atol + rtol * abs(expected)`.
- Defaults unchanged for every integer magnitude in use. Verified: no task
  in either content repo compares integers >= 10^7; the uint8 band at
  defaults is 2.6e-5, below any real difference.
- The rule holds exactly at every magnitude, including integers beyond
  float range.

## Non-goals

- No change to the `Options` tolerance defaults or option names.
- No tolerance for non-numeric dtypes (bool, datetime, structured, object,
  complex) or for `set`/`frozenset`.
- No `Fraction` arithmetic in numpy vectorized paths; float arrays stay
  on float64 and integer arrays use exact uint64 arithmetic.

## Decisions

| Decision | Choice |
|---|---|
| Integer semantics | Uniform rule, no gating: the same `atol + rtol * abs(expected)` as floats (chosen over gated and atol-only variants) |
| Huge ints (beyond float range) | Exact fallback via `fractions.Fraction`; an exact-comparison fallback would violate the rule (e.g. `10**5000` vs `10**5000 + 1` is within the default band) |
| Integer arrays | Exact: difference in modular uint64 arithmetic against the floored tolerance (same rule as scalars at any 64-bit magnitude); `np.array_equal` short-circuit when equal, and exact `np.array_equal` only when `rtol == 0 and atol == 0` |
| numpy integer scalars | Normalize with `operator.index` before arithmetic (uint8 wraparound) |
| int against float | The difference is taken exactly (`Fraction`), and the `==` shortcut is skipped: `int - float` and numpy `int == float` round the int to float first, hiding differences beyond `2**53` |

## Design

### The rule

For every pair of real numbers (floats, Python ints, numpy integer
scalars):

```python
diff = abs(actual - expected)
delta = atol + rtol * abs(expected)
equal = diff <= delta
```

Fast path in plain float arithmetic. When the float computation raises
`OverflowError` (expected magnitude beyond about 1e315, or a huge int
against a float), recompute both sides exactly:

```python
delta = Fraction(atol) + Fraction(rtol) * abs(expected)
diff = abs(actual - expected)  # int / Fraction arithmetic, never overflows
```

`Fraction(float)` is the exact binary value of the float, and
`Fraction * int` never overflows. Unlike `Decimal`, there is no context
trap that silently rounds at 28 digits.

Guards this forces:

- Single NaN fails early, before the fallback (`Fraction(nan)` raises
  `ValueError`); both-NaN passes as today.
- `math.isinf` runs only on non-integral operands (`math.isinf(10**4000)`
  itself raises `OverflowError`).
- numpy scalars are normalized via `operator.index` first, so the
  fallback sees only pure Python types (avoids numpy hijacking
  `Fraction * np.uint8` into float64).

### array_diff.py

Both guards dispatch on `dtype.kind`. Floats use `np.allclose`/`np.isclose`.
Integers with a tolerance use `_int_not_close`: `isclose` promotes to
float64, which would call `2**62 + 1` close to `2**62` even at `atol=0.5`
(the scalar path correctly fails it). Instead the difference is taken in
modular uint64 arithmetic (exact for any 64-bit integer, no wraparound
because `max - min` is never negative) and compared against
`floor(atol + rtol * abs(expected))`, which is equivalent because the
difference is an integer. At `rtol == 0 and atol == 0` integers use
`np.array_equal`. The mask is shared by `array_compare` and
`array_diff_details`, so the issue #207 "no differing indices"
contradiction cannot reappear. Failure details for float and integer
arrays end with `(tolerance: rtol=..., atol=...)`, matching the scalar
path (a visible change to float array failure output).

`Options` rejects negative, infinite, and NaN `relative_tolerance` and
`absolute_tolerance`: a negative tolerance has no meaning, and the array
and scalar paths would disagree on it (the uint64 cast in
`_int_not_close` is undefined for negatives and NaN).

### deep_compare._walk_number

Delete the both-integral exact branch and unify on the rule with the
guards above. An `OverflowError` from the float path routes to the
Fraction fallback instead of reporting a mismatch.

### Behavior changes

- uint8/integer arrays and integer scalars honor `rtol`/`atol` (the fix
  for #217).
- Integers >= 10^7 can differ by 1 and pass at defaults (the rtol band
  reaches 1). No task in either content repo compares integers in that
  regime; integer comparisons at defaults are 10^4 to 10^6 (primes,
  counts), where the band stays below 1.
- `test_integers_compare_exactly` (`1_000_000_001` vs `1_000_000_000`)
  flips to pass; it encodes the old spec. Replaced by two tests: small
  ints stay exact at defaults, and exactness for large ints requires
  `rtol=0`.
- `10**5000` vs `10**5000 + 1` flips to pass (within the 10^4993 band).
  Its repr-safety purpose is preserved by comparing `10**5000` vs
  `2 * 10**5000`, which fails beyond the band.

## Testing

- Issue repro: uint8 arrays and `np.uint8` scalars with `atol=1.0` (the
  real `gaussian_filter` config) — difference of 1 passes, difference of
  2 fails; details consistent with the decision (issue #207). Also
  `atol=2.0` (the issue's quoted repro): difference of 1 passes,
  difference of 3 fails.
- Default band: int array values at 10^7 with difference 1 pass at
  defaults; small ints still exact.
- Exact integer arrays: int64 `2**62 + 1` vs `2**62` fails at
  `rtol=0, atol=0` and at `rtol=0, atol=0.5`, passes at `atol=1.0`;
  int64/uint64 extremes do not wrap.
- Fraction fallback: `10**5000` vs `10**5000 + 1` passes at defaults; vs
  `2 * 10**5000` fails with a repr-safe message; `10**400` vs `1.0` fails
  without raising.
- `rtol=0, atol=2.0` on huge ints applies atol exactly.
- bool/datetime/structured arrays stay exact.
- numpy uint8 scalar normalization: `np.uint8(254)` vs `np.uint8(255)`
  with `atol=2` passes (no wraparound).
- Existing grader-level tolerance tests stay unchanged.

## Process

- Branch `integer-tolerance` off main; fix commits reference #217.
