import unittest

import pytest

from generic_grader.random.random_func_return_range import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_random_func_return_range_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_random_func_return_range_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestRandomFuncReturnRange"


def test_random_func_return_range_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_random_func_return_range_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_random_func_return_range_0")


# Cases Tested:
# 1. Correct returned value
# 2. Passing case with init options specified
# 3. Expected set is larger than the returned set
# 4. Returned set is larger than the expected set


cases = [
    {  # Correct returned value
        "submission": "import random as r\ndef test_function():\n    return r.randint(1, 10)",
        "reference": "pass",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            expected_set={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
        ),
        "doc_func_test_string": (
            """Check the range of value(s) returned from your"""
            """ `submission.test_function` function"""
            """ when called as `test_function()`"""
            """ matches the expected range."""
        ),
    },
    {  # Passing case with init options specified
        "submission": "import random as r\ndef test_function():\n    return r.randint(1, 10)",
        "reference": "pass",
        "result": "pass",
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            expected_set={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
            init=lambda: None,
        ),
        "doc_func_test_string": (
            """Check the range of value(s) returned from your"""
            """ `submission.test_function` function"""
            """ when called as `test_function()`"""
            """ matches the expected range."""
        ),
    },
    {  # Expected set is larger than the returned set
        "submission": "import random as r\ndef test_function():\n    return r.randint(1, 10)",
        "reference": "pass",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            expected_set={1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11},
        ),
        "message": "Items in the second set but not the first",
        "doc_func_test_string": (
            """Check the range of value(s) returned from your"""
            """ `submission.test_function` function"""
            """ when called as `test_function()`"""
            """ matches the expected range."""
        ),
    },
    {  # Returned set is larger than the expected set
        "submission": "import random as r\ndef test_function():\n    return r.randint(1, 10)",
        "reference": "pass",
        "result": AssertionError,
        "options": Options(
            obj_name="test_function",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            expected_set={1, 2, 3, 4, 5, 6, 7, 8, 9},
        ),
        "message": "Items in the first set but not the second",
        "doc_func_test_string": (
            """Check the range of value(s) returned from your"""
            """ `submission.test_function` function"""
            """ when called as `test_function()`"""
            """ matches the expected range."""
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
    built_instance = built_class(methodName="test_random_func_return_range_0")
    test_method = built_instance.test_random_func_return_range_0

    return case, test_method


def test_random_func_return_range(case_test_method):
    """Test response of test_submitted_files function."""
    case, test_method = case_test_method

    if case["result"] == "pass":
        test_method()  # should not raise an error
        assert test_method.__score__ == case["options"].weight
        assert test_method.__doc__ == case["doc_func_test_string"]

    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
        assert test_method.__doc__ == case["doc_func_test_string"]
        assert test_method.__score__ == 0
