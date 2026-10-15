# Generic Grader

A collection of generic tests for grading programming assignments.

**This project is still in very early development.  Expect breaking changes.**

## Installation

``` bash
pip install generic-grader
```

## Usage

1. Name the reference solution `reference.py`, and place it in a `tests`
   subdirectory of the directory containing the student's code.

2. Add a configuration file for the assignment in the `tests` subdirectory (e.g.
   `tests/config.py`).  It might look something like this:

   ``` python
   from parameterized import param
   from generic_grader.style import comments  # Import the tests you want to use
   from generic_grader.utils.options import Options

   # Create tests by calling each test type's build method.
   # They should all start with the word `test_` to be discovered by unittest.
   # Adding a number after `test_` can be used to control the run order.
   # The argument is a list of `param` objects, each with an `Options` object.
   # See the Options class for more information on the available options.
   test_01_TestCommentLength = comments.build(
       [
           param(
               Options(
                   sub_module="hello_user",
                   hint="Check the volume of comments in your code.",
                   entries=("Tim the Enchanter",),
               ),
           ),
           param(
               Options(
                   sub_module="hello_user",
                   hint="Check the volume of comments in your code.",
                   entries=("King Arthur",),
               ),
           ),
       ]
   )
   ```

3. Run the tests.

   ``` bash
   python -m unittest tests/config.py
   ```

### Instructor log for grader faults

When a security error is raised from library code (for example matplotlib
writing its font cache), the student sees a short "bug in the autograder"
message.  The full traceback is logged to the `generic_grader` logger, which is
silent by default so that it cannot end up in student-visible test output.

To show it to instructors only, attach a handler to the real `sys.__stdout__`
in the script that runs the tests (e.g. `run_tests.py`).  Test runners such as
Gradescope's `JSONTestRunner` replace `sys.stdout` and `sys.stderr` with
per-test buffers, but not `sys.__stdout__`.  Gradescope shows the script's
stdout as "Autograder Output" to the teaching team unless `stdout_visibility`
is set.

``` python
import logging
import sys

logging.getLogger("generic_grader").addHandler(logging.StreamHandler(sys.__stdout__))
```

## Grading Octave / MATLAB code

`generic-grader` can also run tests against GNU&nbsp;Octave scripts and
function files (with the same syntax MATLAB uses).  The runtime is
selected per-test via `Options.language`:

``` python
from parameterized import param
from generic_grader.output import output_lines_match_reference
from generic_grader.utils.options import Options

test_01_HelloWorld = output_lines_match_reference.build(
    [
        param(
            Options(
                language="octave",
                sub_module="hello_world",       # → hello_world.m in the CWD
                ref_module="ref_hello_world",   # → ref_hello_world.m (reference)
                obj_name="hello_world",
                weight=1,
            ),
        ),
    ]
)
```

### Prerequisites

* GNU&nbsp;Octave must be installed on the grader host and reachable on
  `PATH`.  On Debian / Ubuntu:

  ``` bash
  sudo apt install octave
  ```

  You can override the executable with the `OCTAVE_EXECUTABLE`
  environment variable if it lives outside the default location.

* The runtime is POSIX-only — the language-independent sandbox uses
  `preexec_fn` to apply `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_FSIZE`, and
  `RLIMIT_NOFILE` to the Octave child, which requires Linux or macOS.

### Script vs. function mode

The Octave runtime picks between two dispatch shapes based on whether
the test passes `args`/`kwargs`:

* **Script mode** — no `args`, no `kwargs`.  The `.m` file is run
  top-to-bottom.  The reference and student files may live under
  different stems (e.g. `main.m` and `ref_main.m`); each side runs
  its own file.
* **Function mode** — any `args` or `kwargs` supplied.  The runtime
  calls `<obj_name>(<args>)`, so the file must define a function with
  that name (either as the top-of-file function of `<stem>.m` or as
  a subfunction inside it).  Positional arguments are serialized as
  Octave scalars; keyword arguments become trailing `('key', value)`
  pairs — the same convention functions like `plot` already use.

Supported argument types in this release are `bool`, `int`, `float`,
and `str`.  Cell arrays, structs, and numpy arrays are planned for
follow-on releases.

### Supported test types

These test types work with `language="octave"` today:

* `file.file_presence` — language-agnostic filename check.
* `output.output_lines_match_reference` — diffs the tee'd I/O log
  produced by the Octave subprocess against the reference's log.
* `output.output_values_match_reference` — extracts numeric values
  from the log with the same regex used for Python; works with
  `%d`, `%f`, and `%e` conversions in `fprintf`.
* `output.output_lines_are_random` — runs the submission twice and
  demands the logs differ.  Octave's `randi`/`rand` reseed at
  interpreter startup so the subprocess-per-call model gives fresh
  randomness without any extra setup.
* `file.file_lines_match_reference` — diffs student-produced and
  reference-produced files line-by-line.  The `@reference_test`
  decorator handles renaming produced files to `sub_<name>` /
  `ref_<name>` between runs.
* `file.file_lines_span_range` — set-equality check on the lines
  written to a file.
* `file.file_has_n_lines` — line-count comparison.
* `file.file_lines_are_random` — runs the submission twice via two
  fresh Octave subprocesses and asserts the produced files differ.
* `file.file_is_identical` — byte-for-byte comparison; strict about
  trailing whitespace and line endings.
* `function.function_return_values_match_reference` — compares the
  value(s) returned by the student's Octave function against the
  reference's.  Return values are captured via a JSON sidecar
  written by `jsonencode` inside the Octave subprocess and decoded
  on the Python side; scalars round-trip as `int`/`float`, row/col
  vectors as `numpy.ndarray`, and multi-return `[a, b] = f(x)` as
  Python tuples.
* `function.function_random_return_length` — asserts `len(f(...))`
  falls in an expected set of lengths.  Works for Octave functions
  that return sized objects (row vectors, matrices); bare scalars
  correctly trigger the standard “did not return a value that has
  a length” hint.
* `function.random_func_return_range` — collects the set of scalar
  return values across repeated calls and asserts it matches an
  `expected_set`.  Octave scalars come back as Python `float`, so
  `expected_set` values should be floats too.

Follow-on releases will add plot tests
(`image.plot_prop_matches_reference`) and a language guard for
the AST/inspect-based tests (`style.*`, `class_.*`, and
`function.static_loop_depth`) that fundamentally can't run against
`.m` files.

### Sandbox

The security sandbox is deliberately language-independent — the same
resource limits apply to Python and Octave runs.  For Octave that
means a fresh subprocess per call with a scrubbed environment
(only `PATH`, `HOME`, `LANG`, `LC_ALL`, and `TMPDIR` are forwarded),
`OCTAVE_HISTFILE=/dev/null`, and the resource limits above.  Wall-clock
enforcement uses `subprocess.communicate(timeout=...)`; the whole
process group is killed on timeout so runaway `.m` files can't leave
grandchildren behind.


## Contributing

1. Clone the repo onto your machine.

   - HTTPS

     ``` bash
     git clone https://github.com/Purdue-EBEC/generic-grader.git
     ```

   - SSH

     ``` bash
     git clone git@github.com:Purdue-EBEC/generic-grader.git
     ```

2. Set up a new virtual environment in the cloned repo.

   ``` bash
   cd generic-grader
   python3.12 -m venv .env3.12
   ```

3. Activate the virtual environment.  If you are using VS Code, there may be a
   pop-up to do this automatically when working from this directory.

   - Linux/macOS

      ``` bash
      source .env3.12/bin/activate
      ```

   - Windows

     ``` bash
     .env3.12\Scripts\activate
     ```

4. Install tesseract-ocr

   - on Linux

     ``` bash
     sudo apt install tesseract-ocr
     ```

   - on macOS

     ``` bash
     brew install tesseract
     ```

   - on Windows, download the latest installers from https://github.com/UB-Mannheim/tesseract/wiki

5. Install ghostscript

   - on Linux

     ``` bash
     sudo apt install ghostscript
     ```

   - on macOS

     ``` bash
     brew install ghostscript
     ```

   - on Windows, download the latest installers from https://ghostscript.com/releases/gsdnld.html

6. Install the package.  Note that this installs the package as editable, so
   edits will be automatically reflected in the installed package.

   ``` bash
   pip install -e .[dev]
   ```
   or

   ``` bash
   uv sync --extra dev
   ```

7. Install the pre-commit hooks. The `commit-msg` hook type is what enforces
   conventional commit messages locally, so install it explicitly.

   ``` bash
   pre-commit install
   pre-commit install --hook-type commit-msg
   ```

8. Run the tests.

   ``` bash
   pytest
   ```

9. Make changes ...

10. Deactivate the virtual environment.

   ``` bash
   deactivate
   ```

## Releasing

Releases are versioned and documented with
[commitizen](https://commitizen-tools.github.io/commitizen/). Commit messages
and pull request titles must follow the
[Conventional Commits](https://www.conventionalcommits.org/) format
(`feat:`, `fix:`, `docs:`, `build:`, `ci:`, `chore:`, ...). Pull requests are
rebase-merged, so every commit lands on `main` individually and the **commit
messages** are what appear in the changelog. Keep PR history clean and
conventional; the local `commit-msg` hook enforces this, and a CI job that
checks the PR title is a backstop.

To cut a release:

1. Make sure `main` is up to date and the working tree is clean.
2. Run `make bump`. This bumps the version in `pyproject.toml` and `uv.lock`,
   prepends a new section to `CHANGELOG.md`, commits, and creates an annotated
   `vX.Y.Z` tag.
3. Review the commit and changelog with `git log -1` and `git show`.
4. Run `make publish` to build, upload to PyPI, and push the tag.

By default commitizen only bumps for `feat`, `fix`, `perf`, and `refactor`
commits. If the commits since the last release are only `docs`, `build`, or
`chore`, `cz bump` fails with `NO_COMMITS_TO_BUMP`; force a patch bump with
`uv run cz bump --increment PATCH --changelog` (or add `--allow-no-commit` to
bump even when no eligible commits are found). If the bump commit is rejected
by the local `commit-msg` hook (for example because a pre-commit hook
auto-fixed a file), re-run with `uv run cz bump --retry`.

While the project is at `0.x`, breaking changes bump the minor version (for
example `0.2.10` to `0.3.0`) rather than the major version.
