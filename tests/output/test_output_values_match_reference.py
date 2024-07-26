import unittest

import pytest
from parameterized import param

from generic_grader.output.output_values_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    o = Options()
    the_params = param(o)
    return build([the_params])


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_output_values_match_reference_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_output_values_match_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestOutputValuesMatchReference"


def test_output_values_match_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_output_values_match_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_output_values_match_reference_0")


# Cases Tested:
# Passing cases:
#   1. All values match
#   2. Only nth (3rd) value matches - should pass as value_n=3 is specified
# Failing cases:
#   3. Only nth (3rd) value does not match
#   4. Some values match and some don't
#   5. Not enough values in required line
#   6. Too many values in required line
#   7. Test to check if docstring is being correctly generated
#   8. Index error case


cases = [
    {  # All values match
        "submission": "def main():\n    print('1,2,3,4,5')",
        "reference": "def main():\n    print('1,2,3,4,5')",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the values on output line 1 from your `main` function"
            " when called as `main()` match the reference values."
        ),
    },
    {  # Only nth (3rd) value matches - should pass as value_n=3 is specified
        "submission": "def main():\n    print('10,20,3,40,50')",
        "reference": "def main():\n    print('1,2,3,4,5')",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            value_n=3,
        ),
        "doc_func_test_string": (
            "Check that the 3rd value on output line 1 from your `main`"
            " function when called as `main()` match the reference values."
        ),
    },
    {  # Only nth (3rd) value does not match
        "submission": "def main():\n    print('1,2,30,4,5')",
        "reference": "def main():\n    print('1,2,3,4,5')",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            value_n=3,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": (
            "Check that the 3rd value on output line 1 from your `main`"
            " function when called as `main()` match the reference values."
        ),
    },
    {  # Some values match and some don't
        "submission": "def main():\n    print('10,2,3,40,50,6,7,8,90,10')",
        "reference": "def main():\n    print('1,2,3,4,5,6,7,8,9,10')",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": (
            "Check that the values on output line 1 from your `main` function"
            " when called as `main()` match the reference values."
        ),
    },
    {  # Not enough values in required line
        "submission": "def main():\n    print('10,20')",
        "reference": "def main():\n    print('10,20,30')",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": (
            "Check that the values on output line 1 from your `main` function"
            " when called as `main()` match the reference values."
        ),
    },
    {  # Too many values in required line
        "submission": "def main():\n    print('10,20,30,40')",
        "reference": "def main():\n    print('10,20,30')",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": (
            "Check that the values on output line 1 from your `main` function"
            " when called as `main()` match the reference values."
        ),
    },
    {  # Test to check if docstring is being correctly generated
        "submission": (
            "def main():\n"
            "    num1 = int(input('Enter a number: '))\n"
            "    num2 = int(input('Enter a number: '))\n"
            "    print(f'The sum of {num1} and {num2+10} = {num1*num2}')"
        ),
        "reference": (
            "def main():\n"
            "    num1 = int(input('Enter a number: '))\n"
            "    num2 = int(input('Enter a number: '))\n"
            "    print(f'The sum of {num1} and {num2} = {num1+num2}')"
        ),
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=(
                "10",
                "20",
            ),
            weight=1,
            line_n=3,
            value_n=2,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": (
            "Check that the 2nd value on output line 3 from your `main`"
            " function when called as `main()` with entries=('10', '20')"
            " match the reference values."
        ),
    },
    {  # Index error case
        "submission": (
            "def main():\n"
            "    num1 = int(input('Enter a number: '))\n"
            "    num2 = int(input('Enter a number: '))\n"
            "    print(f'The sum of {num1} and {num2+10} = ')"
        ),
        "reference": (
            "def main():\n"
            "    num1 = int(input('Enter a number: '))\n"
            "    num2 = int(input('Enter a number: '))\n"
            "    print(f'The sum of {num1} and {num2} = {num1+num2}')"
        ),
        "result": IndexError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=(
                "10",
                "20",
            ),
            weight=1,
            line_n=3,
            value_n=3,
        ),
        "message": "Looking for the 3rd value in the 3rd output line",
        "doc_func_test_string": (
            "Check that the 3rd value on output line 3 from your `main`"
            " function when called as `main()` with entries=('10', '20')"
            " match the reference values."
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

    the_params = [
        param(
            case["options"],
        )
    ]

    built_class = build(the_params)
    built_instance = built_class(methodName="test_output_values_match_reference_0")
    test_method = built_instance.test_output_values_match_reference_0

    return case, test_method


def test_output_values_match_reference(case_test_method):
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
