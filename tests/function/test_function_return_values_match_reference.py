import unittest

import pytest

from generic_grader.function.function_return_values_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_function_return_values_match_reference_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_function_return_values_match_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFunctionReturnValuesMatchReference"


def test_function_return_values_match_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_function_return_values_match_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_function_return_values_match_reference_0")


# Cases Tested:
# 1. Correct returned value
# 2. Returned value is almost equal to expected value
# 3. Type difference in returned values
# 4. Value difference in returned values


cases = [
    {  # Correct returned value
        "submission": "def test_function():\n    return [True, 1, 'abcd', [1,2]]",
        "reference": "def test_function():\n    return [True, 1, 'abcd', [1,2]]",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    },
    {  # Returned value is almost equal to expected value
        "submission": "def test_function():\n    return 0.9999999999",
        "reference": "def test_function():\n    return 1.0",
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as"""
            """ `test_function()` match the reference value(s)."""
        ),
    },
    {  # Type difference in returned values
        "submission": "def test_function():\n    return 1234",
        "reference": "def test_function():\n    return '1234'",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the type of the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as """
            """`test_function()` match the reference value(s)."""
        ),
    },
    {  # Value difference in returned values
        "submission": "def test_function():\n    return 12345",
        "reference": "def test_function():\n    return 1234",
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "message": "Double check the value(s) returned",
        "doc_func_test_string": (
            """Check that the value(s) returned from your"""
            """ `submission.test_function` function when called as """
            """`test_function()` match the reference value(s)."""
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
    built_instance = built_class(
        methodName="test_function_return_values_match_reference_0"
    )
    test_method = built_instance.test_function_return_values_match_reference_0

    return case, test_method


def test_function_return_values_match_reference(case_test_method):
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
