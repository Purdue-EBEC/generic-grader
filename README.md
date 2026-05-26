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
   maintainer-side update to install `isolate` (see the install steps below).

   - on Ubuntu (24.04 tested) -- `isolate` isn't packaged in apt, so
     build from source.  The full sequence, verified end-to-end:

     ``` bash
     # Build dependencies.  asciidoc is needed for the manpages; if
     # you'd rather skip the ~30 MB of asciidoc deps, you can build
     # just the binary targets, but `make all` (which `make install`
     # depends on) builds the manpages by default.
     sudo apt install build-essential libcap-dev libseccomp-dev libsystemd-dev pkg-config asciidoc

     # Clone and build.
     git clone https://github.com/ioi/isolate.git
     cd isolate
     make all
     sudo make install

     # Create the unprivileged user isolate maps containerized
     # processes into, and give it a subuid/subgid range.  On Ubuntu,
     # `useradd --system` does NOT auto-populate /etc/sub{u,g}id, so
     # the second command is required.
     sudo useradd --system --no-create-home --shell /usr/sbin/nologin isolate
     sudo usermod --add-subuids 524288-589823 --add-subgids 524288-589823 isolate

     # Start the cgroup-keeper daemon installed by `make install`.
     # The unit file is shipped to /usr/local/lib/systemd/system/,
     # which systemd scans by default.
     sudo systemctl daemon-reload
     sudo systemctl enable --now isolate.service

     # Smoke-test the install -- both commands should succeed.
     sudo isolate --init --cg --box-id 0
     sudo isolate --cleanup --cg --box-id 0
     ```

     If `make all` emits Python `SyntaxWarning: invalid escape
     sequence '\S'` lines, ignore them -- they come from the asciidoc
     toolchain on Python 3.12+ and don't affect the build.

     If `isolate --init` reports `Cannot open /run/isolate/cgroup`,
     the cgroup-keeper service isn't running -- re-run the
     `systemctl enable --now isolate.service` line above and check
     `systemctl status isolate.service`.

   - other Linux distributions: same procedure -- the package names
     for the build dependencies vary, but `useradd`, `usermod
     --add-subuids`, and `systemctl enable --now isolate.service`
     are identical.  See the
     [isolate README](https://github.com/ioi/isolate?tab=readme-ov-file#installation)
     for distro-specific notes.

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
