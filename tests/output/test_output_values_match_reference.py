import unittest

import pytest
from parameterized import param

from generic_grader.output.output_values_match_reference_merged import build
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
# 1. Correct output
# 2. Correct output with init function
# 3. Wrong output with one input
# 4. Wrong output with multiple inputs
# 5. Not enough values in required line
# 6. Too many values in required line
# 7. Wrong second output with value_n=2
# 8. Wrong second and third output with value_n=2
# 9. Wrong second and third output with value_n=3
# 10. Index error case


cases = [
    {  # Correct output with one input
        "submission": "def main():\n    num = int(input('Enter a number: '))\n    print(f'The number you entered: {num}')",
        "reference": "def main():\n    num = int(input('Enter a number: '))\n    print(f'The number you entered: {num}')",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("10",),
            weight=1,
        ),
        "doc_func_test_string": "Check that the values on output line 1 from your `main` function when called as `main()` with entries=('10',) match the reference values.",
    },
    {  # Correct output with multiple inputs
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1 + num2}')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1 + num2}')",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("10", "20"),
            weight=1,
        ),
        "doc_func_test_string": "Check that the values on output line 1 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Wrong output with one input
        "submission": "def main():\n    num = int(input('Enter a number: '))\n    print(f'The number you entered: {10000}')",
        "reference": "def main():\n    num = int(input('Enter a number: '))\n    print(f'The number you entered: {num}')",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            entries=("10",),
            weight=1,
            line_n=2,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": "Check that the values on output line 2 from your `main` function when called as `main()` with entries=('10',) match the reference values.",
    },
    {  # Wrong output with multiple inputs
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1*num2}')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2}')",
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
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": "Check that the values on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Not enough values in required line
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = ')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2}')",
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
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": "Check that the values on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Too many values in required line
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = ')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2} {num1-num2} {num2/num1}')",
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
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": "Check that the values on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Wrong second output with value_n=2
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2+30} = {num1+num2}')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2}')",
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
        "doc_func_test_string": "Check that the 2nd value on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Wrong second and third output with value_n=2
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2+10} = {num1*num2}')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2}')",
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
        "doc_func_test_string": "Check that the 2nd value on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Wrong second and third output with value_n=3
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2+10} = {num1*num2}')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2}')",
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
            value_n=3,
        ),
        "message": "Your output values did not match the expected values.",
        "doc_func_test_string": "Check that the 3rd value on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
    },
    {  # Index error case
        "submission": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2+10} = ')",
        "reference": "def main():\n    num1 = int(input('Enter a number: '))\n    num2 = int(input('Enter a number: '))\n    print(f'The sum of {num1} and {num2} = {num1+num2}')",
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
        "doc_func_test_string": "Check that the 3rd value on output line 3 from your `main` function when called as `main()` with entries=('10', '20') match the reference values.",
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
        # assert test_method.__score__ == case["score"] # Doesn't work with IndexError case
