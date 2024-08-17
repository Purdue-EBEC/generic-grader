import unittest

import pytest

from generic_grader.file.file_closed import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class_type(built_class):
    """Test that the file_closed build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFileClosed"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_file_closed_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_file_closed_0.__doc__
    assert "Check that all files are closed after calling `main()`." == docstring


passing_cases = [
    {
        "file_text": "def main():\n    pass\n",
        "options": Options(weight=1, ref_module="ref", sub_module="sub"),
    },
    {
        "file_text": "def main():\n    with open('file.txt', 'w') as f:\n        pass\n",
        "options": Options(
            weight=1, ref_module="ref", sub_module="sub", filenames=("file.txt",)
        ),
    },
    {
        "file_text": "def main():\n    f = open('file.txt', 'w')\n    f.close()\n",
        "options": Options(
            weight=1, ref_module="ref", sub_module="sub", filenames=("file.txt",)
        ),
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_cases(case, fix_syspath):
    """Test that the test method passes when the file is closed."""
    # Write the file text to the submission and reference files.
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["file_text"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["file_text"])
    # Create the test parameters and build the test class.
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_closed_0")
    test_method = built_instance.test_file_closed_0
    # Run the test method.
    test_method()
    assert test_method.__score__ == test_method.__weight__


failing_cases = [
    {  # One file is not closed.
        "sub_file_text": "def main():\n    open('file.txt', 'w')\n",
        "ref_file_text": "def main():\n    with open('file.txt', 'w') as f:\n        pass\n",
        "options": Options(
            weight=1, ref_module="ref", sub_module="sub", filenames=("file.txt",)
        ),
        "message": "Your `main` function failed to close the file `file.txt` when called\n  as `main()`.",
    },
    {  # Two files are not closed.
        "sub_file_text": "def main():\n    f = open('file.txt', 'w')\n    x = open('file2.txt', 'w')\n",
        "ref_file_text": "def main():\n    with open('file.txt', 'w') as f:\n        pass\n    with open('file2.txt', 'w') as x:\n        pass\n",
        "options": Options(
            weight=1,
            ref_module="ref",
            sub_module="sub",
            filenames=("file.txt", "file2.txt"),
        ),
        "message": "Your `main` function failed to close the files `file.txt` and\n  `file2.txt` when called as `main()`.",
    },
    {  # A hint is provided.
        "sub_file_text": "def main():\n    open('file.txt', 'w')\n",
        "ref_file_text": "def main():\n    with open('file.txt', 'w') as f:\n        pass\n",
        "options": Options(
            weight=1,
            ref_module="ref",
            sub_module="sub",
            filenames=("file.txt",),
            hint=" This is a hint.",
        ),
        "message": "Your `main` function failed to close the file `file.txt` when called\n  as `main()`. This is a hint.",
    },
    {  # The student opens a file not opened in the reference.
        "sub_file_text": "def main():\n    open('file.txt', 'w')\n",
        "ref_file_text": "def main():\n    pass\n",
        "options": Options(weight=1, ref_module="ref", sub_module="sub"),
        "message": "Your `main` function failed to close the file `file.txt` when called\n  as `main()`.",
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_failing_cases(case, fix_syspath):
    """Test that the test method fails when the file is not closed."""
    # Write the file text to the submission and reference files.
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file_text"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file_text"])
    # Create the test parameters and build the test class.
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_closed_0")
    test_method = built_instance.test_file_closed_0
    # Run the test method.
    with pytest.raises(AssertionError) as exc_info:
        test_method()
    # Check that the correct message is raised.
    assert case["message"] in str(exc_info.value)
    assert test_method.__score__ == 0
