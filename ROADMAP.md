# Roadmap

This file tracks larger architectural efforts in the generic-grader.
Day-to-day work happens on individual issues; this is a coarse-grained
view of the in-flight projects.

## Sandbox isolation (Layer 3) — issue [#98](https://github.com/Purdue-EBEC/generic-grader/issues/98)

**Status:** In progress. The single-PR effort delivers an
`isolate`-backed sandbox that runs student submissions in a fresh
process per call, with the legacy in-process path kept as the default
until everything is wired through end-to-end.

| Layer | What it does | Status |
| ----- | ------------ | ------ |
| 1 — pure patches | The legacy in-process patches in `utils/user.py` and `utils/patches.py`. Still the default. | Shipped. |
| 2 — resource limits | `resource` / `signal`-based time and memory caps applied in-process. | Shipped. |
| 3 — sandbox isolation | Length-prefixed JSON protocol; `isolate`-driven subprocess; Python runtime; Octave runtime stub; opt-in via `Options.use_sandbox=True`. | This PR. |

### How to opt in

Set `use_sandbox=True` on the `Options` for a given test.  Any patches
that need to cross the sandbox boundary must be expressed as
`PatchSpec` instances (see `generic_grader.sandbox.patch_specs`)
because live callables can't be JSON-serialized.

```python
from generic_grader.sandbox.patch_specs import make_noop_patch_spec
from generic_grader.utils.options import Options

opts = Options(
    use_sandbox=True,
    patch_specs=(make_noop_patch_spec("submission.cleanup_temp_files"),),
)
```

When `use_sandbox=False` (the default), the grader behaves exactly as
it did before this PR.

### What's next after this PR

- **Octave runtime:** the stub in `sandbox/octave_runtime.py` returns
  a structured "not implemented" error today.  Filling it in is a
  straight swap.
- **`ref_dir` bind-mount:** `Options.ref_dir` is defined now but only
  consumed in a single test-resolution path.  The follow-up will
  bind-mount it read-only under `/box/reference` so reference code
  and submissions are properly isolated.
- **Deprecate Layer 1 patches:** once Layer 3 is the default, the
  legacy in-process patches should be removed from `utils/user.py`.

## Other planned work

See the [issue tracker](https://github.com/Purdue-EBEC/generic-grader/issues)
for the full list.
