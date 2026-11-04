# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Curated sections use Keep a Changelog headings (`Added`/`Changed`/`Fixed`),
while commitizen-generated sections use its type names
(`Feat`/`Fix`/`Refactor`/`Perf`). Version headings use the `v`-prefixed tag
form (`## v0.2.10`) to match commitizen's generated sections.

## v0.4.0 (2026-11-04)

### BREAKING CHANGE

- integers now compare within the same rtol/atol band as floats.
At the default rtol=1e-7, integer values >= 1e7 can differ by 1 and still pass;
set rtol=0 and atol=0 on the Options for exact integer comparison. Options
also raises ValueError for negative or non-finite tolerances.

### Fix

- apply tolerance rule to integers and compare ints against floats exactly (#217)
  - Integer scalars, huge ints and integer arrays follow the same
    `abs(actual - expected) <= atol + rtol * abs(expected)` rule as floats.
  - Mixed int/float comparisons use an exact difference, so values beyond 2**53
    no longer pass by rounding. `timedelta64` stays exact.
  - `Options` rejects negative, infinite, and NaN `relative_tolerance` and
    `absolute_tolerance`.
  - Array failure details end with a single `(tolerance: ...)` line.

## v0.3.0 (2026-10-21)

### Feat

- report callable comparison as an autograder misconfiguration
- apply float tolerance to output values and plot properties
- compare returned collections with float tolerance
- add tolerance-aware recursive deep_compare utility

### Fix

- harden deep_compare number and type-mismatch paths
- restore string diff in deep_compare failure details
- terminate deep_compare on self-referential lists and dicts
- drop "for this test" from the time limit message
- give imports their own time limit
- allow library cleanup during grader patch-target imports

## v0.2.10 (2026-10-06)

### Added

- Thread `rtol`/`atol` through `array_diff_details` for tolerance-aware array
  comparisons (#207).
- Support Python 3.14 in CI.

### Changed

- Allow trusted library operations during student imports (#200).
- Attribute library-origin security errors to the grader rather than the
  student.

### Fixed

- Select a non-interactive matplotlib backend at runtime to avoid cold-start
  timeouts (#205).
- Give `Options.expected_distribution` a per-instance default.
- Make the unclosed-file message deterministic.
- Fix test message checks that iterated over characters.
