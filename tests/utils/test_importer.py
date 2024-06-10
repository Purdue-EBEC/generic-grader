from types import FunctionType

import pytest

from generic_grader.utils.importer import Importer


class FakeTest:
    """Create a custom class to imitate a test object."""

    def fail(self, msg):  # We need to re-raise these exceptions to run the tests.
        if "Stuck at call to `input()` while importing" in msg:
            raise Importer.InputError(msg)
        elif "Unable to import" in msg:
            raise AttributeError(msg)
        elif "ModuleNotFound" in msg:  # This is the fake exception we raise.
            raise ModuleNotFoundError(msg)
        else:  # If we get a different error message, raise a generic exception. This is to catch any other exceptions that may be raised and fail pytest tests that would otherwise pass.
            raise Exception(
                msg
            )  # pragma: no cover # This line is not covered by tests because we are not testing for this case.


def test_input_error(monkeypatch, tmp_path):
    """Test the Importer's ability to catch global input() calls."""
    # Create a fake file using tmp_path in order to avoid pytest coverage errors.
    fake_file = tmp_path / "fake_module.py"
    fake_file.write_text("input()\nfake_func = lambda: None")
    # Switch to the fake file's directory.
    monkeypatch.chdir(tmp_path)
    # Create a FakeTest object to pass to the Importer.
    test = FakeTest()
    # Run the Importer with a fake module and function name.
    with pytest.raises(Importer.InputError):
        Importer.import_obj(test, "fake_module", "fake_func")


def test_other_error(monkeypatch, tmp_path):
    """Test the Importer's ability to catch other exceptions. This raises a ModuleNotFoundError."""

    fake_file = tmp_path / "fake_module_1.py"
    fake_file.write_text("input()\nfake_func = lambda: None")
    monkeypatch.chdir(tmp_path)

    test = FakeTest()

    with pytest.raises(ModuleNotFoundError):
        Importer.import_obj(test, "fake_module_0", "fake_func")


def test_attribute_error(monkeypatch, tmp_path):
    """Test the Importer's ability to catch missing objects."""

    fake_file = tmp_path / "fake_module.py"
    fake_file.write_text("fake_func = lambda: None")
    monkeypatch.chdir(tmp_path)

    test = FakeTest()

    with pytest.raises(AttributeError):
        Importer.import_obj(test, "fake_module", "fake_obj")


def test_ignores_function_input(monkeypatch, tmp_path):
    """Test the Importer's ability to not catch input() calls inside functions."""

    fake_file = tmp_path / "fake_module.py"
    fake_file.write_text("def fake_func():\n  input()\n  return None")
    monkeypatch.chdir(tmp_path)

    test = FakeTest()

    obj = Importer.import_obj(test, "fake_module", "fake_func")
    assert isinstance(obj, FunctionType)


def test_valid_import(monkeypatch, tmp_path):
    """Test the Importer's ability to import a valid object."""
    fake_file = tmp_path / "fake_module.py"
    fake_file.write_text("fake_func = lambda: None")
    monkeypatch.chdir(tmp_path)

    test = FakeTest()

    obj = Importer.import_obj(test, "fake_module", "fake_func")
    assert isinstance(obj, FunctionType)
