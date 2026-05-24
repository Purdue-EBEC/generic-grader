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
        # Tests the except block on line 51
        "module": "fake_module",
        "error": Importer.InputError,
        "text": "input('foo', bar='spam')\nfake_func = lambda: None",
        "message": "Stuck at call to `input()` while importing `fake_func`",
        "object": "fake_func",
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

    fake_file = fix_syspath / (case["module"] + ".py")
    fake_file.write_text(case["text"])

    test = FakeTest()
    with pytest.raises(case["error"]):
        Importer.import_obj(test, case["module"], Options(obj_name=case["object"]))


@pytest.mark.parametrize("case", error_cases)
def test_error_message(fix_syspath, case):
    """Test the Importer's ability to provide helpful error messages."""
    fake_file = fix_syspath / (case["module"] + ".py")
    fake_file.write_text(case["text"])
    test = FakeTest()
    #  Since we already check Exception type, we can use a generic Exception here
    with pytest.raises(Exception) as exc_info:
        Importer.import_obj(test, case["module"], Options(obj_name=case["object"]))
    assert case["message"] in str(exc_info.value)


missing_dependency_cases = [
    {
        # Tests missing top-level module import.
        "module": "fake_module",
        "object": "fake_obj",
        "files": {},
        "expected_messages": [
            "Unable to import `fake_module`.",
            "Make sure you have submitted a module named `fake_module`",
            "contains the definition of `fake_obj`.",
        ],
    },
    {
        # Tests nested missing dependency through another imported file.
        "module": "fake_module",
        "object": "fake_obj",
        "files": {
            "fake_module.py": "import fake_dependency\nfake_obj = lambda: None",
            "fake_dependency.py": "import fake_inner_module\nhelper = 1",
        },
        "expected_messages": [
            "Unable to import `fake_module`.",
            "imports `fake_inner_module`",
            "could not be found.",
            "in `fake_dependency.py` on line 1:",
        ],
    },
    {
        # Tests missing dependency wrapped in another ModuleNotFoundError.
        "module": "fake_module",
        "object": "fake_obj",
        "files": {
            "fake_module.py": "import fake_dependency\nfake_obj = lambda: None",
            "fake_dependency.py": (
                "try:\n"
                "    import fake_inner_module\n"
                "except ModuleNotFoundError as err:\n"
                "    raise ModuleNotFoundError(name='fake_dependency_proxy') from err\n"
            ),
        },
        "expected_messages": [
            "Unable to import `fake_module`.",
            "imports `fake_inner_module`",
            "in `fake_dependency.py` on line 2:",
        ],
    },
    {
        # Tests dotted module import where the parent package is missing.
        # Python raises ModuleNotFoundError(name='fake_pkg'), not name='fake_pkg.submod',
        # so the prefix check is required to avoid a misleading dependency hint.
        "module": "fake_pkg.submod",
        "object": "fake_obj",
        "files": {},
        "expected_messages": [
            "Unable to import `fake_pkg.submod`.",
            "Make sure you have submitted a module named `fake_pkg.submod`",
            "contains the definition of `fake_obj`.",
        ],
    },
]


@pytest.mark.parametrize("case", missing_dependency_cases)
def test_nested_missing_dependency_message(fix_syspath, case):
    """Importer should report clear messages for missing dependencies."""
    for file_name, file_text in case["files"].items():
        fake_file = fix_syspath / file_name
        fake_file.write_text(file_text)

    test = FakeTest()
    with pytest.raises(ModuleNotFoundError) as exc_info:
        Importer.import_obj(test, case["module"], Options(obj_name=case["object"]))

    for expected_message in case["expected_messages"]:
        assert expected_message in str(exc_info.value)


def test_import_location_hint_returns_none_when_all_frames_filtered(monkeypatch):
    """If every traceback frame is inside `generic_grader`, the hint should
    be None instead of pointing at grader internals.
    """
    import traceback

    from generic_grader.utils import importer as importer_mod

    FrameSummary = traceback.FrameSummary
    fake_tb = [
        FrameSummary(
            "/site-packages/generic_grader/utils/patches.py",
            150,
            "safe_import",
            line="return real_import(name, globals, locals, fromlist, level)",
        )
    ]
    monkeypatch.setattr(importer_mod.traceback, "extract_tb", lambda _: fake_tb)

    assert Importer._import_location_hint(ModuleNotFoundError("x")) is None


def test_import_location_hint_falls_back_when_source_line_unavailable(monkeypatch):
    """When the chosen frame has no source line, the hint should omit the
    backtick-quoted snippet but still include the filename and line number.
    """
    import traceback

    from generic_grader.utils import importer as importer_mod

    FrameSummary = traceback.FrameSummary
    fake_tb = [FrameSummary("student.py", 7, "<module>", line=None)]
    monkeypatch.setattr(importer_mod.traceback, "extract_tb", lambda _: fake_tb)

    hint = Importer._import_location_hint(ModuleNotFoundError("x"))
    assert hint == "The error occurred in `student.py` on line 7."
