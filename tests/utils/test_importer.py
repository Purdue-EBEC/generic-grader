import unittest
from types import FunctionType

import pytest

from generic_grader.utils.exceptions import ExitError, QuitError, UserTimeoutError
from generic_grader.utils.importer import Importer
from generic_grader.utils.options import Options


class FakeTest(unittest.TestCase):
    """A fake test class for testing"""


def test_valid_import(fix_syspath):
    """Test the Importer's ability to import a valid object."""
    # Create a fake module
    fake_file = fix_syspath / "fake_module.py"
    fake_file.write_text("fake_func = lambda: None")
    # Create a fake test object
    test = FakeTest()
    # Import the fake object
    obj = Importer.import_obj(test, "fake_module", Options(obj_name="fake_func"))
    # Check that the object is a function
    assert isinstance(obj, FunctionType)


def test_submodule_import(fix_syspath):
    """Test the Importer's ability to import a valid object from a submodule."""
    # Create a fake module
    fake_file = fix_syspath / "tests" / "fake_module.py"
    fake_file.parent.mkdir()
    fake_file.write_text("fake_func = lambda: None")
    # Create a fake test object
    test = FakeTest()
    # Import the fake object
    obj = Importer.import_obj(test, "tests.fake_module", Options(obj_name="fake_func"))
    # Check that the object is a function
    assert isinstance(obj, FunctionType)


def test_ignores_function_input(fix_syspath):
    """Test the Importer's ability to not catch input() calls inside functions."""

    fake_file = fix_syspath / "fake_module.py"
    fake_file.write_text("def fake_func():\n  input()\n  return None")

    test = FakeTest()

    obj = Importer.import_obj(test, "fake_module", Options(obj_name="fake_func"))
    assert isinstance(obj, FunctionType)


error_cases = [
    {
        # Tests the except block on line 39
        "module": "fake_module",
        "error": AttributeError,
        "text": "fake_func = lambda: None",
        "message": "Unable to import `fake_obj`",
        "object": "fake_obj",
    },
    {
        # Tests the except block on line 51
        "module": "fake_module",
        "error": Importer.InputError,
        "text": "input()\nfake_func = lambda: None",
        "message": "Stuck at call to `input()` while importing `fake_func`",
        "object": "fake_func",
    },
    {
        # Tests the except block on line 65
        "module": "fake_module",
        "error": ModuleNotFoundError,
        "message": "\n  Unable to import `fake_module`.\n\nHint:\n  Make sure you have submitted a file named `fake_module.py and it\n  contains the definition of `fake_obj`.",
        "object": "fake_obj",
    },
    {  # Test quit_error
        "module": "fake_module",
        "error": QuitError,
        "text": "quit()",
        "message": "",  # This is a QuitError, which is already tested in test_exceptions.py
        "object": "fake_func",
    },
    {
        # Test exit_error
        "module": "fake_module",
        "error": ExitError,
        "text": "exit()",
        "message": "",  # This is an ExitError, which is already tested in test_exceptions.py
        "object": "fake_func",
    },
    {
        # Test timeout_error
        "module": "fake_module",
        "error": UserTimeoutError,
        "text": "import time\ntime.sleep(10)",
        "message": "",  # This is a UserTimeoutError, which is already tested in test_exceptions.py
        "object": "fake_func",
    },
]


@pytest.mark.parametrize("case", error_cases)
def test_error_exception(fix_syspath, case):
    """Test the Importer's ability to raise the correct exception."""

    if case["error"] is not ModuleNotFoundError:
        fake_file = fix_syspath / (case["module"] + ".py")
        fake_file.write_text(case["text"])

    test = FakeTest()
    with pytest.raises(case["error"]):
        Importer.import_obj(test, case["module"], Options(obj_name=case["object"]))


@pytest.mark.parametrize("case", error_cases)
def test_error_message(fix_syspath, case):
    """Test the Importer's ability to provide helpful error messages."""
    if case["error"] is not ModuleNotFoundError:
        fake_file = fix_syspath / (case["module"] + ".py")
        fake_file.write_text(case["text"])
    test = FakeTest()
    #  Since we already check Exception type, we can use a generic Exception here
    with pytest.raises(Exception) as exc_info:
        Importer.import_obj(test, case["module"], Options(obj_name=case["object"]))
    assert case["message"] in str(exc_info.value)
