# Generic Grader

A collection of generic tests for grading programming assignments.


## Usage

Don't use this yet. It's not ready.


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
   python3.11 -m venv .env3.11
   ```

3. Activate the virtual environment.  If you are using VS Code, there may be a pop-up to do this automatically when working from this directory.

   - Linux/macOS

      ``` bash
      source .env3.11/bin/activate
      ```

   - Windows

     ``` bash
     .env3.11\Scripts\activate
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

5. Install other dependencies.

   ``` bash
   pip install -r common/requirements.txt
   ```

6. Install the pre-commit hooks.

   ``` bash
   pre-commit install
   ```

7. Install the package.  Note that this installs the package as editable, so
   edits will be automatically reflected in the installed package.

   ``` bash
   pip install -e .[code_style]
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
