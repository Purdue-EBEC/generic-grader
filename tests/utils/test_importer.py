import sys
import unittest
from types import FunctionType

import pytest

from generic_grader.utils.importer import Importer


@pytest.fixture(scope="module", autouse=True)
def fix_syspath():
    """
    This is the current solution to the empty string being missing
    from sys.path when running pytest."""
    old_path = sys.path.copy()
    sys.path.insert(0, "")
    yield
    sys.path = old_path


class FakeTest(unittest.TestCase):
    """A fake test class for testing"""


def test_valid_import(monkeypatch, tmp_path):
    """Test the Importer's ability to import a valid object."""
    # Create a fake module
    fake_file = tmp_path / "fake_module_0.py"
    fake_file.write_text("fake_func = lambda: None")
    # Change to the directory where the fake module is located
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Import the fake object
    obj = Importer.import_obj(test, "fake_module_0", "fake_func")
    # Check that the object is a function
    assert isinstance(obj, FunctionType)


def test_ignores_function_input(monkeypatch, tmp_path):
    """Test the Importer's ability to not catch input() calls inside functions."""

    fake_file = tmp_path / "fake_module_1.py"
    fake_file.write_text("def fake_func():\n  input()\n  return None")
    monkeypatch.chdir(tmp_path)

    test = FakeTest()

    obj = Importer.import_obj(test, "fake_module_1", "fake_func")
    assert isinstance(obj, FunctionType)


error_cases = [
    {
        # Tests the except block on line 39
        "module": "fake_module_2",
        "error": AttributeError,
        "text": "fake_func = lambda: None",
        "message": "Unable to import `fake_obj`",
        "object": "fake_obj",
    },
    {
        # Tests the except block on line 51
        "module": "fake_module_3",
        "error": Importer.InputError,
        "text": "input()\nfake_func = lambda: None",
        "message": "Stuck at call to `input()` while importing `fake_func`",
        "object": "fake_func",
    },
    {
        # Tests the except block on line 65
        "module": "fake_module_4",
        "error": ModuleNotFoundError,
        "message": "Error while importing `fake_obj`",
        "object": "fake_obj",
    },
]


@pytest.mark.parametrize("case", error_cases)
def test_error_exception(monkeypatch, tmp_path, case):
    """Test the Importer's ability to raise the correct exception."""

    if case["error"] is not ModuleNotFoundError:
        fake_file = tmp_path / (case["module"] + ".py")
        fake_file.write_text(case["text"])
        monkeypatch.chdir(tmp_path)

    test = FakeTest()
    with pytest.raises(case["error"]):
        Importer.import_obj(test, case["module"], case["object"])


@pytest.mark.parametrize("case", error_cases)
def test_error_message(monkeypatch, tmp_path, case):
    """Test the Importer's ability to provide helpful error messages."""
    if case["error"] is not ModuleNotFoundError:
        fake_file = tmp_path / (case["module"] + ".py")
        fake_file.write_text(case["text"])
        monkeypatch.chdir(tmp_path)

    test = FakeTest()
    #  Since we already check Exception type, we can use a generic Exception here
    with pytest.raises(Exception) as exc_info:
        Importer.import_obj(test, case["module"], case["object"])
    assert case["message"] in str(exc_info.value)