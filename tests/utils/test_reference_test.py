import os
import unittest

import pytest

from generic_grader.utils.exceptions import RefFileNotFoundError
from generic_grader.utils.options import Options
from generic_grader.utils.reference_test import make_diff, reference_test

reference_cases = [
    {
        "ref_text": "def main():\n    print('Hello World!')",
        "sub_text": "def main():\n    print('Hello World!')",
        "options": Options(sub_module="sub_test", ref_module="ref_test"),
    },
    {
        "ref_text": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Hello World!')",
        "sub_text": "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Hello World!')",
        "options": Options(
            sub_module="sub_test", ref_module="ref_test", filenames=("file.txt",)
        ),
    },
]


@pytest.fixture(scope="function", params=reference_cases)
def reference_case(request, fix_syspath):
    case = request.param
    ref_file = fix_syspath / "ref_test.py"
    ref_file.write_text(case["ref_text"])
    sub_file = fix_syspath / "sub_test.py"
    sub_file.write_text(case["sub_text"])
    return case


def test_user_creation(reference_case):
    """Test that the reference and student users are created."""
    case = reference_case
    o = case["options"]

    class FakeTest:
        @reference_test
        def test(self, options):
            assert hasattr(self, "ref_user")
            assert hasattr(self, "student_user")
            assert self.ref_user.options == options

    ft = FakeTest()
    ft.test(o)


def test_file_creation(reference_case):
    """Test that the reference and student files are created."""
    case = reference_case
    o = case["options"]

    class FakeTest(unittest.TestCase):
        @reference_test
        def test(self, options):
            files = os.listdir()
            for filename in options.filenames:
                assert "ref_" + filename in files
                assert "sub_" + filename in files

    ft = FakeTest()
    ft.test(o)


def test_missing_reference_file(fix_syspath):
    """Test that the correct exception is raised after the reference generated file is not found."""
    ref_file = fix_syspath / "ref_test.py"
    ref_file.write_text("def main():\n    print('Hello World!')")
    sub_file = fix_syspath / "sub_test.py"
    sub_file.write_text(
        "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Hello World!')"
    )
    o = Options(sub_module="sub_test", ref_module="ref_test", filenames=("file.txt",))

    class FakeTest(unittest.TestCase):
        @reference_test
        def test(self, options):
            """This can do nothing because we are testing the decorator."""

    ft = FakeTest()
    with pytest.raises(RefFileNotFoundError):
        ft.test(o)


def test_missing_student_file(fix_syspath):
    """Test that the correct exception is raised after the student generated file is not found."""
    ref_file = fix_syspath / "ref_test.py"
    ref_file.write_text(
        "def main():\n    with open('file.txt', 'w') as f:\n        f.write('Hello World!')"
    )
    sub_file = fix_syspath / "sub_test.py"
    sub_file.write_text("def main():\n    print('Hello World!')")
    o = Options(sub_module="sub_test", ref_module="ref_test", filenames=("file.txt",))

    class FakeTest(unittest.TestCase):
        @reference_test
        def test(self, options):
            """This can do nothing because we are testing the decorator."""

    ft = FakeTest()
    with pytest.raises(FileNotFoundError):
        ft.test(o)


make_diff_cases = [
    {
        "actual": "Hello World!",
        "expected": "Hello World!",
        "expected_diff": "  Hello World!\n",
    },
    {
        "actual": "Hello World!",
        "expected": "Hello World",
        "expected_diff": "- Hello World!\n?            -\n+ Hello World\n",
    },
    {
        "actual": "Hello World",
        "expected": "Hello World!",
        "expected_diff": "- Hello World\n+ Hello World!\n?            +\n",
    },
]


@pytest.mark.parametrize("case", make_diff_cases)
def test_make_diff(case):
    """Test that the make_diff function works as expected."""
    diff = make_diff(case["actual"], case["expected"])
    assert diff == case["expected_diff"]


def test_init(fix_syspath, capsys):
    """Test that the init function is called."""
    ref_file = fix_syspath / "ref_test.py"
    ref_file.write_text("def main():\n    print('Hello World!')")
    sub_file = fix_syspath / "sub_test.py"
    sub_file.write_text("def main():\n    print('Hello World!')")

    def init():
        print("init")

    o = Options(sub_module="sub_test", ref_module="ref_test", init=init)

    class FakeTest(unittest.TestCase):
        @reference_test
        def test(self, options):
            """This can do nothing because we are testing the decorator."""

    ft = FakeTest()
    ft.test(o)
    captured = capsys.readouterr()
    assert captured.out == "init\n"
