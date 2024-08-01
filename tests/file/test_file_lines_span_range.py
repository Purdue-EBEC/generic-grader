import unittest

import pytest

from generic_grader.file.file_lines_span_range import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    o = Options(filenames=("ref_file.txt",), sub_module="hello_user")
    return build(o)


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_build_class(built_class):
    """Test that the build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFileLinesSpanRange"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_lines_span_range_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_lines_span_range_0.__doc__
    assert (
        "Check that the range of values written to the file `ref_file.txt` from your `hello_user.main` function when called as `main()` spans the expected range."
        == docstring
    )


passing_cases = [
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n    with open('file2.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n    with open('file2.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "options": Options(
            filenames=("file.txt", "file2.txt"), sub_module="sub", ref_module="ref"
        ),
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n1\\n2\\n1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2')\n",
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n1\\n2')\n",
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_cases(case, fix_syspath):
    """Test that the expected values pass the test."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file"])
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_lines_span_range_0")
    built_instance.test_lines_span_range_0()


failing_cases = [
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n6\\n')\n",
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
        "error": "Hint:\n  The values written to your output file do not span the expected set\n  of values.  Double check the values written to the file `file.txt`\n  by your `main` function when called as `main()`.",
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n')\n",
        "options": Options(filenames=("file.txt",), sub_module="sub", ref_module="ref"),
        "error": "Hint:\n  The values written to your output file do not span the expected set\n  of values.  Double check the values written to the file `file.txt`\n  by your `main` function when called as `main()`.",
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n    with open('file2.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n    with open('file2.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n6\\n')\n",
        "options": Options(
            filenames=("file.txt", "file2.txt"), sub_module="sub", ref_module="ref"
        ),
        "error": "Hint:\n  The values written to your output files do not span the expected set\n  of values.  Double check the values written to the files `file.txt`\n  and `file2.txt` by your `main` function when called as `main()`.",
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n    with open('file2.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n5\\n')\n    with open('file2.txt', 'w') as f:\n        f.write('1\\n2\\n3\\n4\\n')\n",
        "options": Options(
            filenames=("file.txt", "file2.txt"), sub_module="sub", ref_module="ref"
        ),
        "error": "Hint:\n  The values written to your output files do not span the expected set\n  of values.  Double check the values written to the files `file.txt`\n  and `file2.txt` by your `main` function when called as `main()`.",
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_failing_cases(case, fix_syspath):
    """Test that the failing cases fail."""
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_file"])
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_file"])
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_lines_span_range_0")
    with pytest.raises(AssertionError) as exc_info:
        built_instance.test_lines_span_range_0()
    assert case["error"] in str(exc_info.value)
