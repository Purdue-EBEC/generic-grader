# Design: tolerance-aware comparison of collections

Date: 2026-10-15
Status: Approved (pending spec review)

## Problem

A student's `rgb_to_hsv(236, 215, 151)` passed locally and failed on Gradescope:

```text
Tuples differ: (31.999999999999996, 91.84322033898306, 236.0)
            != (32.00000000000001, 91.84322033898306, 236.0)
```

The values differ by about 1e-14, far inside the default tolerance, but the
function returns a tuple. `function_return_values_match_reference` only applies
tolerance to top-level `np.ndarray` and `np.floating` values (`rtol`/`atol` via
`np.isclose`) and to top-level `float` (`assertAlmostEqual`, 7 places).
Everything else, including tuples, lists and dicts of floats or arrays, falls
through to `safe_assert_equal`, which is an exact `==`.

Other graders compare with exact `==` in the same way:
`instance_attributes_match_reference`, `output_values_match_reference` and
`plot_prop_matches_reference`.

An earlier attempt (`better_collection_comparisons`, Feb 2026, one WIP commit)
added 11 failing test cases and an analysis document but no implementation. That
branch is 84 commits behind main, so this work starts on a fresh branch
(`collection-comparisons`) off main. The old branch is left untouched; its test
cases are ported.

## Goals

- Floats and numpy arrays compare with tolerance at any nesting depth inside
  lists, tuples and dicts.
- Failure messages name the path of the first failing element.
- Comparison terminates on self-referential structures.
- One shared implementation used by every grader that compares values.

## Non-goals

- No change to the `rtol`/`atol` options themselves or their defaults.
- No tolerance inside `set`/`frozenset` (floats and hashing do not mix).
- No handling of numpy object arrays that contain themselves.

## Decisions

| Decision | Choice |
|---|---|
| Scope | All exact-`==` graders (return values, attributes, output values, plot props) |
| Float tolerance | Unified: every float uses `np.isclose` with `Options.relative_tolerance` and `Options.absolute_tolerance`; bare-`float` `assertAlmostEqual` is retired |
| Nested type checking | Strict at every level for return values and attributes; numeric-by-value for values parsed from output text (`3` equals `3.0`) |
| Approach | New recursive `deep_compare` returning `(equal, details)`, extending the existing `array_compare` contract |

Rejected: unittest `addTypeEqualityFunc` (cannot report paths or carry
tolerances); wrapping floats in an `approx`-style class (mutates values, fragile
with numpy and arbitrary student objects).

## Design

### Module

New `src/generic_grader/utils/deep_compare.py`:

```python
def deep_compare(
    actual,
    expected,
    rtol: float = DEFAULT_RTOL,
    atol: float = DEFAULT_ATOL,
    strict_types: bool = True,
    max_samples: int = 5,
) -> tuple[bool, str]: ...
```

`details` is `""` when equal, otherwise a string beginning with `"\nDetails: "`
to match `array_compare`, so callers append their hint message unchanged.

### Dispatch (on `type(expected)`)

| `expected` | Behavior |
|---|---|
| `np.ndarray` | Delegate to `array_compare` (dtype, shape, `rtol`/`atol`) |
| `float`, `np.floating` | `np.isclose(actual, expected, rtol, atol, equal_nan=True)` |
| `list`, `tuple` | Same length, then compare element by element in order |
| `dict` | Same key set (order ignored), then compare values per key |
| `set`, `frozenset` | Exact `==` |
| anything else | `==`, guarded: an exception or non-bool result counts as a failure |

Student values can be arbitrary objects, so every access to `actual` (`type`,
`len`, indexing, `==`) is wrapped and a raised exception is reported as a
mismatch, as `array_compare` already does.

### Type checking

Before dispatching, with `strict_types=True`, require
`isinstance(actual, type(expected))`. A mismatch (tuple vs list, `int` vs
`float`, `np.float64` vs `float`) fails with a type message and the path.

With `strict_types=False` (used by `output_values_match_reference` and
`plot_prop_matches_reference`), real numbers compare by value, so `3` matches
`3.0`; container types must still match.

### Paths and reporting

Paths accumulate as the walk descends, e.g. `[1]['a'][2]`. Each failure reports
`expected=` and `actual=` using the truncated `reprlib` settings already in
`safe_equal`. Up to `max_samples` failures are collected before the walk stops.
The module does not use `difflib`, so the O(n^2) concern behind
`safe_assert_equal` does not apply.

### Cycle safety

A list or dict may contain itself (`a = []; a.append(a)`). The walk keeps a set
of `(id(actual), id(expected))` pairs currently being compared. Meeting a pair
already in progress counts as equal for that pair (the standard coinductive
assumption), so the walk terminates on any finite object graph. The pair is
removed on the way out so shared, non-cyclic substructures are still compared
each time they appear. A student cycle against a finite reference fails by
ordinary structural mismatch, and `repr` of cyclic values is safe (`[...]`,
`reprlib` depth limit).

### Integration

| Grader | Change |
|---|---|
| `function_return_values_match_reference` | Replace the ndarray / `np.floating` / `float` / `safe_assert_equal` branching with `deep_compare(..., strict_types=True)`; keep the top-level `assertIsInstance` type hint |
| `instance_attributes_match_reference` | `deep_compare(..., strict_types=True)` per attribute |
| `output_values_match_reference` | `deep_compare(..., strict_types=False)` |
| `plot_prop_matches_reference` | `deep_compare(..., strict_types=False)`; existing `assertAlmostEqual(error, 0, delta=0.01)` path unchanged |

Each grader raises `AssertionError(details + hint_message)` as it does today.
`safe_assert_equal` stays for the graders that compare plain text or counts.

### Behavior changes

- Bare-`float` comparison switches from 7 decimal places to `rtol`/`atol`.
- Nested elements are type-checked strictly for return values and attributes, so
  `[1]` no longer matches `[1.0]` there.
- Tuples, lists and dicts of floats now pass within tolerance.

## Testing

Tests use pytest and follow the layout of the existing per-grader test files.

- Port the 11 cases from the old branch (tuple / list / dict of arrays and
  floats, nested lists).
- Regression for the reported failure:
  `(31.999999999999996, 91.84322033898306, 236.0)` vs
  `(32.00000000000001, 91.84322033898306, 236.0)`.
- Nested tolerance; `np.ndarray` inside a dict; NaN.
- Length mismatch, key mismatch, order-insensitive dict, set mismatch.
- Strict type failures (tuple vs list, `int` vs `float`) and the relaxed
  `strict_types=False` mode (`3` vs `3.0`).
- **Cycles:** a list containing itself and a dict containing itself, each
  compared against an equal cyclic structure (must pass) and a different cyclic
  structure (must fail), plus a student cycle against a finite reference. All
  must terminate without `RecursionError`.
- Path reporting: assert the failure message contains the expected path.
- Unit tests for `deep_compare` in `tests/utils/`, plus grader-level cases in
  each affected grader's test file.

## Process

- Work happens on `collection-comparisons`, branched from main.
- Commits use conventional-commit messages (`feat:`, `fix:`, `test:`, `docs:`)
  so commitizen can generate the changelog. `CHANGELOG.md` is not edited by
  hand.
- Behavior changes above are noted in the body of the `feat:` commit; mark it
  `feat!:` / `BREAKING CHANGE:` if the version policy treats retiring
  `assertAlmostEqual` as breaking.
