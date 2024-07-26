import unittest

import pytest

from generic_grader.file.file_lines_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(filenames=("ref_file.txt",), sub_module="hello_user"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class(built_class):
    """Test that the build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFileLinesMatchReference"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_file_lines_match_reference_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_file_lines_match_reference_0.__doc__
    assert (
        "Check that the lines written to the file `ref_file.txt` from your"
        " `hello_user.main` function when called as `main()` match the"
        " reference."
    ) == docstring


hello_world = (
    "def main():\n"
    "    with open('file.txt', 'w') as f:\n"
    "        f.write('Hello, world!')\n"
)

goodbye_world = hello_world.replace("Hello", "Goodbye")

hello_goodbye = hello_world + (
    "    with open('file2.txt', 'w') as f:\n        f.write('Goodbye, world!')\n"
)

goodbye_hello = goodbye_world + (
    "    with open('file2.txt', 'w') as f:\n        f.write('Hello, world!')\n"
)

noop = "def main():\n    pass\n"

passing_cases = [
    {  # Check that it works with a single file
        "ref_file": hello_world,
        "sub_file": hello_world,
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
    },
    {  # Check that it works with multiple files
        "ref_file": hello_goodbye,
        "sub_file": hello_goodbye,
        "options": Options(
            filenames=("file.txt", "file2.txt"), sub_module="sub", ref_module="ref"
        ),
    },
    {  # Check that only specified files are tested
        "ref_file": hello_world,
        "sub_file": hello_goodbye,
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_cases(case, fix_syspath):
    """Test that the test passes for a given case."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file"])
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_lines_match_reference_0")
    built_instance.test_file_lines_match_reference_0()


failing_cases = [
    {  # Check that it fails when single file contents do not match
        "ref_file": hello_world,
        "sub_file": goodbye_world,
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
        "exception": AssertionError,
        "error": (
            "{'file.txt': ['Goodbye, world!']} != {'file.txt': ['Hello, world!']}\n"
            "- {'file.txt': ['Goodbye, world!']}\n"
            "?                ^ -----\n"
            "\n"
            "+ {'file.txt': ['Hello, world!']}\n"
            "?                ^^^^\n"
            " : \n"
            "\n"
            "Hint:\n"
            "  The lines written to your output file do not match the expected\n"
            "  lines.  Double check the lines written to the file `file.txt` by\n"
            "  your `main` function when called as `main()`."
        ),
    },
    {  # Check that it fails when multiple file contents do not match
        "ref_file": hello_goodbye,
        "sub_file": goodbye_hello,
        "options": Options(
            sub_module="sub", ref_module="ref", filenames=("file.txt", "file2.txt")
        ),
        "exception": AssertionError,
        "error": (
            "{'file.txt': ['Goodbye, world!'], 'file2.txt': ['Hello, world!']} != "
            "{'file.txt': ['Hello, world!'], 'file2.txt': ['Goodbye, world!']}\n"
            "- {'file.txt': ['Goodbye, world!'], 'file2.txt': ['Hello, world!']}\n"
            "?                ^ -----                           ^ ---\n"
            "\n"
            "+ {'file.txt': ['Hello, world!'], 'file2.txt': ['Goodbye, world!']}\n"
            "?                ^^^^                            ^^^^^^\n"
            " : \n"
            "\n"
            "Hint:\n"
            "  The lines written to your output files do not match the expected\n"
            "  lines.  Double check the lines written to the files `file.txt` and\n"
            "  `file2.txt` by your `main` function when called as `main()`."
        ),
    },
    {  # Check that it fails when their are no files to check
        "ref_file": noop,
        "sub_file": noop,
        "options": Options(sub_module="sub", ref_module="ref"),
        "exception": ValueError,
        "error": (
            "There are no files to check."
            "  This test requires filenames to be specified."
        ),
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_failing_cases(case, fix_syspath):
    """Test that the test fails for a given case."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file"])
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_lines_match_reference_0")
    with pytest.raises(case["exception"]) as exc_info:
        built_instance.test_file_lines_match_reference_0()
    assert case["error"] == str(exc_info.value)
