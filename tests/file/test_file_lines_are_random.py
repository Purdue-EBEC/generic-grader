import unittest

import pytest

from generic_grader.file.file_lines_are_random import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(sub_module="hello_user", filenames=("file.txt",)))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class_type(built_class):
    """Test that the file_closed build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFileLinesAreRandom"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_file_lines_are_random_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_file_lines_are_random_0.__doc__
    assert (
        "Check that the lines written to the file `file.txt` from your `hello_user.main` function when called as `main()` are random."
        == docstring
    )


one_file = (
    "def main():\n"
    "    with open('file.txt', 'w') as f:\n"
    "        f.write('Hello, world!')\n"
)

two_files = one_file + (
    "    with open('file2.txt', 'w') as f:\n        f.write('Goodbye, world!')\n"
)
empty_file = "def main():\n    pass\n"
failing_cases = [
    {  # The case where no file name is provided
        "error": ValueError,
        "file_text": empty_file,
        "options": Options(sub_module="sub", ref_module="ref", filenames=()),
    },
    {
        # The case where one file matches
        "error": AssertionError,
        "file_text": one_file,
        "options": Options(sub_module="sub", ref_module="ref", filenames=("file.txt",)),
    },
    {
        # The case where two files match
        "error": AssertionError,
        "file_text": two_files,
        "options": Options(
            sub_module="sub", ref_module="ref", filenames=("file.txt", "file2.txt")
        ),
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_failing_cases(case, fix_syspath):
    """Make sure the test fails when the files match"""
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["file_text"])
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(two_files)
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_lines_are_random_0")
    with pytest.raises(case["error"]):
        built_instance.test_file_lines_are_random_0()


"""In order to generate "random" files, we need to have a way to check that the files are different from one run to the next.
This is a bit tricky to do, but we can use the current time to generate a random file.
We can then check that the file is different from the previous file. """

one_file_time = (
    "import time\n"
    "def main():\n"
    "    with open('file.txt', 'w') as f:\n"
    "        f.write(str(time.time()))\n"
)
two_files_time = one_file_time + (
    "    with open('file2.txt', 'w') as f:\n" "        f.write(str(time.time()))\n"
)
passing_cases = [
    {
        "file_text": one_file_time,
        "options": Options(sub_module="sub", ref_module="ref", filenames=("file.txt",)),
    },
    {
        "file_text": two_files_time,
        "options": Options(
            sub_module="sub", ref_module="ref", filenames=("file.txt", "file2.txt")
        ),
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_cases(case, fix_syspath):
    """Make sure the test passes when the files are different"""
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["file_text"])
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(two_files)
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_lines_are_random_0")
    built_instance.test_file_lines_are_random_0()
