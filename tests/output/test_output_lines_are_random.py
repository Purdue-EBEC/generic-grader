import unittest

import pytest

from generic_grader.output.output_lines_are_random import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_output_lines_are_random_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_output_lines_are_random_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestOutputLinesAreRandom"


def test_output_lines_are_random_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_output_lines_are_random_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_output_lines_are_random_0")


# Cases Tested:
# 1. Printing random output
# 2. Passing with init defined
# 3. Not random output


cases = [
    {  # Printing random output
        "submission": "import random as r\ndef main():\n    for i in range(5):\n        print(r.randint(1, 10))",
        "reference": "import random as r\ndef main():\n    for i in range(5):\n        print(r.randint(1, 10))",
        "result": "pass",
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the lines of output"
            + " from your `submission.main` function"
            + " when called as `main()`"
            + " are random."
        ),
    },
    {  # Passing with init defined
        "submission": "import random as r\ndef main():\n    for i in range(5):\n        print(r.randint(1, 10))",
        "reference": "import random as r\ndef main():\n    for i in range(5):\n        print(r.randint(1, 10))",
        "result": "pass",
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
            init=lambda: None,
        ),
        "doc_func_test_string": (
            "Check that the lines of output"
            + " from your `submission.main` function"
            + " when called as `main()`"
            + " are random."
        ),
    },
    {  # Not random output
        "submission": "import random as r\ndef main():\n    for i in range(5):\n        print('1')",
        "reference": "import random as r\ndef main():\n    for i in range(5):\n        print(r.randint(2, 10))",
        "result": AssertionError,
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the lines of output"
            + " from your `submission.main` function"
            + " when called as `main()`"
            + " are random."
        ),
        "message": "Your output does not appear to be random.",
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
    built_instance = built_class(methodName="test_output_lines_are_random_0")
    test_method = built_instance.test_output_lines_are_random_0

    return case, test_method


def test_output_lines_are_random(case_test_method):
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
