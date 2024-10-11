import unittest

import pytest

from generic_grader.file.file_has_n_lines import build
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
    assert built_class.__name__ == "TestFileHasNLines"


def test_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_file_has_n_lines_0")


def test_doc_func(built_instance):
    """Test that the doc_func function returns the correct docstring."""
    docstring = built_instance.test_file_has_n_lines_0.__doc__
    assert (
        "Check the number of lines written to the file `ref_file.txt` from your `hello_user.main` function when called as `main()`."
        == docstring
    )


passing_cases = [
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
        "options": Options(
            filenames=("file.txt",), sub_module="sub", ref_module="ref", weight=1
        ),
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n    with open('file2.txt', 'w') as f:\n        f.write('Line 1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n    with open('file2.txt', 'w') as f:\n        f.write('Line 1')\n",
        "options": Options(
            filenames=("file.txt", "file2.txt"),
            sub_module="sub",
            ref_module="ref",
            weight=1,
        ),
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1\\nLine 2')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1\\nLine 2')\n",
        "options": Options(
            filenames=("file.txt",), sub_module="sub", ref_module="ref", weight=1
        ),
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1 + spam')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1 no spam')\n",
        "options": Options(
            filenames=("file.txt",), sub_module="sub", ref_module="ref", weight=1
        ),
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_passing_cases(case, fix_syspath):
    """Test that the passing cases pass."""
    ref_file = fix_syspath / "ref.py"
    sub_file = fix_syspath / "sub.py"
    ref_file.write_text(case["ref_file"])
    sub_file.write_text(case["sub_file"])
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_has_n_lines_0")
    test_method = built_instance.test_file_has_n_lines_0
    test_method()
    assert test_method.__score__ == case["options"].weight


failing_cases = [
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1\\nLine 2')\n",
        "options": Options(
            filenames=("file.txt",), sub_module="sub", ref_module="ref", weight=1
        ),
        "error": "Lists differ: [2] != [1]\n\nFirst differing element 0:\n2\n1\n\n- [2]\n+ [1] : \n\nHint:\n  Your output file does not have the expected number of lines.  Double\n  check the number of lines written to the file `file.txt` by your\n  `main` function when called as `main()`.",
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1\\nLine 2')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n",
        "options": Options(
            filenames=("file.txt",), sub_module="sub", ref_module="ref", weight=1
        ),
        "error": "Lists differ: [1] != [2]\n\nFirst differing element 0:\n1\n2\n\n- [1]\n+ [2] : \n\nHint:\n  Your output file does not have the expected number of lines.  Double\n  check the number of lines written to the file `file.txt` by your\n  `main` function when called as `main()`.",
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n    with open('file2.txt', 'w') as f:\n        f.write('Line 1')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n    with open('file2.txt', 'w') as f:\n        f.write('Line 1\\nLine 2')\n",
        "options": Options(
            filenames=("file.txt", "file2.txt"),
            sub_module="sub",
            ref_module="ref",
            weight=1,
        ),
        "error": "Lists differ: [1, 2] != [1, 1]\n\nFirst differing element 1:\n2\n1\n\n- [1, 2]\n?     ^\n\n+ [1, 1]\n?     ^\n : \n\nHint:\n  Your output files do not have the expected number of lines.  Double\n  check the number of lines written to the files `file.txt` and\n  `file2.txt` by your `main` function when called as `main()`.",
    },
    {
        "ref_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n    with open('file2.txt', 'w') as f:\n        f.write('Line 1\\nLine 2')\n",
        "sub_file": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Line 1')\n    with open('file2.txt', 'w') as f:\n        f.write('Line 1')\n",
        "options": Options(
            filenames=("file.txt", "file2.txt"),
            sub_module="sub",
            ref_module="ref",
            weight=1,
        ),
        "error": "Lists differ: [1, 1] != [1, 2]\n\nFirst differing element 1:\n1\n2\n\n- [1, 1]\n?     ^\n\n+ [1, 2]\n?     ^\n : \n\nHint:\n  Your output files do not have the expected number of lines.  Double\n  check the number of lines written to the files `file.txt` and\n  `file2.txt` by your `main` function when called as `main()`.",
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_failing_cases(case, fix_syspath):
    """Test that the failing cases fail."""
    ref_file = fix_syspath / "ref.py"
    sub_file = fix_syspath / "sub.py"
    ref_file.write_text(case["ref_file"])
    sub_file.write_text(case["sub_file"])
    built_class = build(case["options"])
    built_instance = built_class(methodName="test_file_has_n_lines_0")
    test_method = built_instance.test_file_has_n_lines_0

    with pytest.raises(AssertionError) as e:
        test_method()
    assert case["error"] == str(e.value)
    assert test_method.__score__ == 0
