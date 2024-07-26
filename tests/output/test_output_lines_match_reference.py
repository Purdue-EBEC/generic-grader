import unittest

import pytest

from generic_grader.output.output_lines_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_output_lines_match_reference_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_output_lines_match_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestOutputLinesMatchReference"


def test_output_lines_match_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_output_lines_match_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_output_lines_match_reference_0")


# Cases Tested:
# 1. Correct output
# 2. Wrong first line and correct second line with start = 2 - Should pass
#    because only checks second line
# 3. Wrong 1st and 4th line, and correct 2nd and 3rd lines with start = 2 and
#    line_n = 2 - Should pass because only checks line 2-3
# 4. Slightly wrong output test case
# 5. Completely wrong output

cases = [
    {  # Correct output
        "submission": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}!')"
        ),
        "reference": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}!')"
        ),
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("AJ",),
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the formatting of output lines 1 through the end from"
            " your `main` function when called as `main()` with entries=('AJ',)"
            " matches the reference formatting."
        ),
    },
    {
        # Wrong first line and correct second line with start = 2 - Should pass
        # because only checks second line
        "submission": (
            "def main():\n"
            "    name = input('Wrong first line')\n"
            "    print(f'Hello, {name}!')"
        ),
        "reference": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}!')"
        ),
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("AJ",),
            weight=1,
            start=2,
        ),
        "doc_func_test_string": (
            "Check that the formatting of output lines 2 through the end from"
            " your `main` function when called as `main()` with entries=('AJ',)"
            " matches the reference formatting."
        ),
    },
    {
        # Wrong 1st and 4th line, and correct 2nd and 3rd lines with start = 2
        # and line_n = 2 - Should pass because only checks line 2-3
        "submission": (
            "def main():\n"
            "    name = input('Wrong first line')\n"
            "    print(f'Hello, {name}!')\n"
            "    print(f'Hello, {name}!')\n"
            "    print(f'Wrong output')"
        ),
        "reference": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}!')\n"
            "    print(f'Hello, {name}!')"
        ),
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("AJ",),
            weight=1,
            start=2,
            n_lines=2,
        ),
        "doc_func_test_string": (
            "Check that the formatting of output lines 2 through 3 from your"
            " `main` function when called as `main()` with entries=('AJ',)"
            " matches the reference formatting."
        ),
    },
    {  # Slightly wrong output test case
        "submission": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}')"
        ),
        "reference": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}!')"
        ),
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("AJ",),
            weight=1,
        ),
        "message": "Your output did not match the expected output",
        "doc_func_test_string": (
            "Check that the formatting of output lines 1 through the end from"
            " your `main` function when called as `main()` with entries=('AJ',)"
            " matches the reference formatting."
        ),
    },
    {  # Completely wrong output
        "submission": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Wrong output')"
        ),
        "reference": (
            "def main():\n"
            "    name = input('What is your name? ')\n"
            "    print(f'Hello, {name}!')"
        ),
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("AJ",),
            weight=1,
        ),
        "message": "Your output did not match the expected output",
        "doc_func_test_string": (
            "Check that the formatting of output lines 1 through the end from"
            " your `main` function when called as `main()` with entries=('AJ',)"
            " matches the reference formatting."
        ),
    },
]


@pytest.fixture(params=cases)
def case_test_method(request, fix_syspath):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = fix_syspath / f"{case['options'].sub_module}.py"
    file_path.write_text(case["submission"])
    file_path = fix_syspath / f"{case['options'].ref_module}.py"
    file_path.write_text(case["reference"])

    built_class = build(case["options"])
    built_instance = built_class(methodName="test_output_lines_match_reference_0")
    test_method = built_instance.test_output_lines_match_reference_0

    return case, test_method


def test_output_lines_match_reference(case_test_method):
    """Test response of test_submitted_files function."""
    case, test_method = case_test_method

    if case["result"] == "pass":
        test_method()  # should not raise an error
        assert test_method.__score__ == case["score"]
        assert test_method.__doc__ == case["doc_func_test_string"]

    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()

        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
        assert test_method.__doc__ == case["doc_func_test_string"]
        assert test_method.__score__ == case["score"]
