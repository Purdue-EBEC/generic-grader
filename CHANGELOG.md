# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Curated sections use Keep a Changelog headings (`Added`/`Changed`/`Fixed`),
while commitizen-generated sections use its type names
(`Feat`/`Fix`/`Refactor`/`Perf`). Version headings use the `v`-prefixed tag
form (`## v0.2.10`) to match commitizen's generated sections.

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
