# Roadmap

Direction and themes for upcoming releases. Individual tasks live in the
GitHub issue tracker; this file groups them by target milestone.

## v0.6.0

Goal: every ENGR 13300 MATLAB task grades correctly under the Octave sandbox
(see [ENGR 13300 MATLAB graders](#engr-13300-matlab-graders-content-repo)).

v0.5.0 (full diffs for long string mismatches, and `build!:` requiring Python
3.14+ with 3.15 added to the CI matrix) contains none of the Octave work. Draft
PRs #189 to #194 (runtime, output and file tests, return values, plots,
language guard, style tests) are stacked on v0.4.0, and the unprivileged-user
commits (`0443a1e`, `415bb3f`, which add `runtimes/sandbox.py`) sit on top of
them on `feature/octave-unprivileged-user` with no PR yet. The stack is behind
v0.5.0.

- **Land the Octave stack.** Rebase the stack onto `main`, open a PR for the
  unprivileged-user commits, and merge #189 to #194 in order. v0.6.0 is the
  first release with Octave support, so it must wait for this.
- **List arguments for Octave function calls (next).** `options.args` and
  `options.kwargs` accept only bool, int, float and str; a list raises
  `TypeError: Cannot serialize argument ... 'list'`. Blocks four graders: M2
  `ind_1`, M2 `ind_2`, M2 `team_2` and M3 `team_3`. A first version of steps 1 to
  3, with tests, was written but is only in `stash@{0}` on
  `feature/octave-unprivileged-user` (uncommitted, not yet run against the
  graders). Plan, test first:
  1. A flat list of numbers or bools becomes a row vector (`[10, 12]`), and an
     empty list becomes `[]`.
  2. A list of equal-length lists becomes a matrix (`[1, 2; 3, 4]`), so a
     column vector is `[[1], [2]]`. Ragged rows, deeper nesting and strings
     inside a list raise `TypeError`; cell arrays are out of scope.
  3. Keep the exact-type rule: `True` stays `true`, not `1`.
  4. Run the four blocked graders' list cases through `OctaveRuntime`, in
     sandbox and non-sandbox mode.
  5. Commit to the stack (see above) and bump the pin in `content`.
- **Stop copying student files into the grader directory.** The reference's
  script-mode run happens in the same directory that
  `cp /autograder/submission/* .` fills with student files; a student `disp.m`
  or `sum.m` there can shadow Octave builtins in the reference run. Closing
  this also requires `file_presence` and `file_set_up` to look in the
  submission directory.

## v0.7.0

- **Sandbox Python submissions.** Python student code is imported into the
  grader's own interpreter, so a uid drop needs a separate worker process
  (arguments and results over a pipe) that reuses
  `generic_grader.runtimes.sandbox`. Today it relies on the in-process
  security patches only. Draft PR #184 (an earlier `isolate`-based sandbox,
  issue #98) is still open; decide whether it is superseded and close it if so.

## Unscheduled

- **Hide the gnuplot toolkit warning in hints.** Every failed Octave test's hint
  starts with "using the gnuplot graphics toolkit is discouraged", which pushes
  the real error out of view. Likely fix: turn off the
  `Octave:gnuplot-graphics-toolkit` warning (id not yet confirmed) in the
  runtime.

## ENGR 13300 MATLAB graders (content repo)

The `content` repo (`/ENGR/13300/content`, branch `graders`) builds the
Gradescope zips; `make verify-graders` runs each against its own reference
solution. The work below must be done before the graders can be verified.

The `graders` branch pins generic-grader to `415bb3f` and still runs Python
3.13 (`requires-python = ">=3.13,<3.14"` in `pyproject.toml`; `setup.sh` and
`run_autograder` call `python3.13`). Once the Octave work merges to `main`, the
grader must move to Python 3.14 or later: `main` now requires it, so pinning
to a merged commit will not install on 3.13.

### Tasks and graders

22 task directories under `source/Part_6_MATLAB`: 17 have a grader, 5 do not.
The 5 without are written, PDF or docx deliverables (M1 `team_1/a` and
`team_2/b`, M2 `team_1/a`, M3 `team_1/a` and `team_2/a`); no autograder is
planned, so they appear to be graded by hand (confirm).

Passing `make verify-graders` (11): M1 `ind_1/a`, `ind_1/b`, `ind_2/a`,
`pre_0/a`, `team_2/a`, `team_3/a`, `team_3/b`; M2 `pre_0/a`; M3 `ind_2/a`,
`pre_0/a`, `pre_0/b`. Only M3 `ind_2/a` has also been rehearsed on
`ubuntu:22.04` with the sandbox.

Failing (6):

| Task | Tests failed | Ref. score | Cause |
|---|---|---|---|
| M2 `ind_1/a` | 7 of 8 | 1.0 | list args |
| M2 `ind_2/a` | 2 of 3 | 1.0 | list args (secantline); helper names (sugar) |
| M2 `team_2/a` | 1 of 4 | 7.0 | list args (transmission) |
| M2 `team_3/a` | 2 of 3 | 1.0 | helper names (parts a and b) |
| M3 `ind_1/a` | 1 of 2 | 1.0 | helper names, `block.png` |
| M3 `team_3/a` | 2 of 9 | 7.8 | list args (`[100, 200]` and `[0, 1]` cases) |

M3 `team_3/a` was rehearsed on `ubuntu:22.04`: 7.75 of 10, with only the two
list cases failing and the hostile probes blocked. Whether the causes above are
sufficient to make M2 `team_3/a` and M3 `ind_1/a` pass is unconfirmed.

### Work in `content`

1. **Reference helper names.** Several reference solutions call helpers by
   their `_solution` names (for example `ma2_team_2_fractions_solution`), but
   the generator ships those helpers as `ref_*.m`, so the call is undefined.
   Rewrite the calls in the packaged reference to the `ref_` names, as the
   generator already does for Python imports. Do the same in the verification
   copy, mapping to `_username` or `_teamnumber`. Affects M2 `ind_2`, M2
   `team_3` and M3 `ind_1`.
2. **Package `block.png`.** The generator only zips images whose name starts
   with `grader_`, so M3 `ind_1` cannot read `block.png`. Ship it at the zip
   root and list it in `provided_files`.
3. **Clean up the pending edits.** They are committed on `graders` as a single
   `wip` commit (`7307ca1e`): `grader/setup.sh` (Octave from
   `ppa:ubuntuhandbook1/octave`, because 22.04's 6.4 has no `jsonencode`),
   `grader/run_autograder` (copies `*.m`, exports `GENERIC_GRADER_SUBMISSION_DIR`,
   locks `/autograder/source`), the generic-grader pin, and `provided_files` for
   the four CSV tasks (M2 `ind_2` and `team_3`, M3 `ind_2` and `team_3`). Split
   it into conventional commits, drop any stray `pytz` bump from `uv.lock`, and
   hold the push until list args merge.
4. **Re-pin generic-grader** to the merged commit (it is `415bb3f` on the
   sandbox branch today) and raise the floor in `pyproject.toml` from
   `>=0.3.0`. Move the grader to Python 3.14 or later (see above; confirm a
   3.14 package source exists for Ubuntu 22.04). Rebuild, and confirm
   `make verify-graders` reports all 17 passing. The v0.3.0 and v0.4.0
   tolerance changes apply to `main` but not to the graders' last verification,
   so reference scores need re-checking.
5. **Rehearse all 17 on `ubuntu:22.04`** with a valid and a hostile submission;
   only two have been done.
6. **Real Gradescope run.** Set the image to Ubuntu 22.04, upload M3 `ind_2/a`
   first, then the rest.
