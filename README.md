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
