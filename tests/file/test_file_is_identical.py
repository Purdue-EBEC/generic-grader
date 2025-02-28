import unittest

import pytest

from generic_grader.file.file_is_identical import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(filenames=("file.txt",), sub_module="sub"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class_type(built_class):
    """Test that the file_closed build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFileIsIdentical"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_file_is_identical_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_file_is_identical_0.__doc__
    assert (
        "Checks the file data written to the file `file.txt` from your `sub.main` function when called as `main()`."
        == docstring
    )


passing_cases = [
    {
        "options": Options(
            ref_module="ref", sub_module="sub", weight=1, filenames=("file.txt",)
        ),
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
    },
    {
        "options": Options(
            ref_module="ref", sub_module="sub", weight=1, filenames=("file.txt",)
        ),
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.writelines(['Line 1', 'Line 2'])\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.writelines(['Line 1', 'Line 2'])\n",
    },
    {
        "options": Options(
            ref_module="ref",
            sub_module="sub",
            weight=1,
            filenames=("file1.txt", "file2.txt"),
        ),
        "ref_file": "def main():\n    with open('file1.txt', 'w') as f, open('file2.txt', 'w') as g:\n        f.write('Line 1')\n        g.write('Line 2')\n",
        "sub_file": "def main():\n    with open('file1.txt', 'w') as f, open('file2.txt', 'w') as g:\n        f.write('Line 1')\n        g.write('Line 2')\n",
    },
    {
        "options": Options(
            ref_module="ref",
            sub_module="sub",
            weight=1,
            filenames=("file1.txt",),
            obj_name="main",
        ),
        "ref_file": "def main():\n    with open('file1.txt', 'wb') as f:\n        f.write(b'\\x00\\x01\\x02\\x03')\n",
        "sub_file": "def main():\n    with open('file1.txt', 'wb') as f:\n        f.write(b'\\x00\\x01\\x02\\x03')\n",
    },
]


failing_cases = [
    {
        "options": Options(
            ref_module="ref", sub_module="sub", weight=1, filenames=("file.txt",)
        ),
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Not Line 1')\n",
        "error": AssertionError,
        "error_message": "The data in `file.txt` does not match the expected data.",
    },
    {
        "options": Options(
            ref_module="ref",
            sub_module="sub",
            weight=1,
            filenames=("file.txt", "file2.txt"),
        ),
        "ref_file": "def main():\n    with open('file.txt', 'w') as f, open('file2.txt', 'w') as g:\n        f.write('Line 1')\n        g.write('Line 2')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f, open('file2.txt', 'w') as g:\n        f.write('Line 1')\n        g.write('Not Line 2')\n",
        "error": AssertionError,
        "error_message": "The data in `file2.txt` does not match the expected data.",
    },
    {
        "options": Options(
            ref_module="ref",
            sub_module="sub",
            weight=1,
            filenames=("file1.txt",),
            obj_name="main",
        ),
        "ref_file": "def main():\n    with open('file1.txt', 'wb') as f:\n        f.write(b'\\x00\\x01\\x02\\x04')\n",
        "sub_file": "def main():\n    with open('file1.txt', 'wb') as f:\n        f.write(b'\\x00\\x01\\x02\\x03')\n",
        "error": AssertionError,
        "error_message": "The data in `file1.txt` does not match the expected data",
    },
    {
        "options": Options(ref_module="ref", sub_module="sub", weight=1),
        "ref_file": "def main():\n    pass\n",
        "sub_file": "def main():\n    pass\n",
        "error": ValueError,
        "error_message": "There are no files to check.  This test requires filenames to be specified.",
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_cases(case, fix_syspath):
    """Test that the test method passes when the files match."""
    # Write the file text to the submission and reference files.
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file"])
    # Create the test parameters and build the test class.
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_is_identical_0")
    test_method = built_instance.test_file_is_identical_0
    # Run the test method.
    test_method()
    assert test_method.__score__ == test_method.__weight__


@pytest.mark.parametrize("case", failing_cases)
def test_failing_cases(case, fix_syspath):
    """Test that the test method fails when the files do not match."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file"])
    # Create the test parameters and build the test class.
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_is_identical_0")
    test_method = built_instance.test_file_is_identical_0

    with pytest.raises(case["error"]) as exc_info:
        test_method()

    assert case["error_message"] in str(exc_info.value)
    assert test_method.__score__ == 0
