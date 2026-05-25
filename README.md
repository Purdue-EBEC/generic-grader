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
   from generic_grader.style import comments # Import the tests you want to use
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

5. Install [isolate](https://github.com/ioi/isolate) (used by the Layer-3
   sandbox; the test suite skips one isolate-dependent smoke test when it
   isn't present, but full coverage runs require it).  The GitHub Actions
   workflow `.github/workflows/pytest.yml` will need a corresponding
   maintainer-side update to add `isolate` to its `apt install` line.

   - on Ubuntu 22.04+

     ``` bash
     sudo apt install isolate
     ```

   - other Linux distributions: build from source per the
     [isolate README](https://github.com/ioi/isolate?tab=readme-ov-file#installation).

   - macOS / Windows: isolate is Linux-only.  Run the sandbox tests in a
     Linux VM or container.  The rest of the test suite still runs on the
     host.

6. Install ghostscript

   - on Linux

     ``` bash
     sudo apt install ghostscript
     ```

   - on macOS

     ``` bash
     brew install ghostscript
     ```

   - on Windows, download the latest installers from https://ghostscript.com/releases/gsdnld.html

7. Install the package.  Note that this installs the package as editable, so
   edits will be automatically reflected in the installed package.

   ``` bash
   pip install -e .[dev]
   ```
   or

   ``` bash
   uv sync --extra dev
   ```

8. Install the pre-commit hooks.

   ``` bash
   pre-commit install
   ```

9. Run the tests.

   ``` bash
   pytest
   ```

10. Make changes ...

11. Deactivate the virtual environment.

   ``` bash
   deactivate
   ```

## Sandbox isolation (Layer 3)

The grader can run a student's submission in a fresh, isolated
subprocess per call rather than in-process.  Set
`Options(use_sandbox=True)` to opt in.  Patches that need to cross
the sandbox boundary must be expressed as `PatchSpec` instances
(see `generic_grader.sandbox.patch_specs`).

The sandbox uses [isolate](https://github.com/ioi/isolate); install
it as part of the contributing setup above.  See [`ROADMAP.md`](ROADMAP.md)
for the rollout plan.
