import os
import unittest

import pytest
from parameterized import param

from generic_grader.style.program_length import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    o = Options()
    the_params = param(o)
    return build(the_params)


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_style_program_length_build_class(built_class):
    """Test that the style program_length build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_style_program_length_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestProgramLength"


def test_style_program_length_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_style_program_length_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_program_length_0")


# Test a file with
#   - okay length
#   - a bit too long
#   - a lot too long
cases = [
    {
        "submission": "pass\n" * 14,
        "reference": "pass\n" * 10,
        "result": "pass",
        "weight": 1,
        "score": 1,
    },
    {
        "submission": "pass\n" * 16,
        "reference": "pass\n" * 10,
        "result": AssertionError,
        "message": "a bit bigger than expected",
        "weight": 1,
        "score": 1,
    },
    {
        "submission": "pass\n" * 25,
        "reference": "pass\n" * 10,
        "result": AssertionError,
        "message": "a lot bigger than expected",
        "weight": 1,
        "score": 0,
    },
]


@pytest.fixture(params=cases)
def case_test_method(request, fix_syspath):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = fix_syspath / "reference.py"
    file_path.write_text(case["reference"])
    file_path = fix_syspath / "submission.py"
    file_path.write_text(case["submission"])

    the_params = [
        param(
            Options(
                weight=case["weight"],
                ref_module="reference",
                sub_module="submission",
            ),
        )
    ]
    built_class = build(the_params)
    built_instance = built_class(methodName="test_program_length_0")
    test_method = built_instance.test_program_length_0

    return case, built_instance, test_method


def test_program_length(case_test_method):
    """Test response of test_submitted_files function."""
    case, built_instance, test_method = case_test_method

    if case["result"] == "pass":
        test_method()
        assert test_method.__score__ == case["score"]
    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            # Here we call the test method directly instead of using the
            # instance's run() method because we want to catch its exception
            # which would otherwise by captured in a TestResult.
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
        assert test_method.__score__ == case["score"]


def test_submodule_program_length(fix_syspath):
    """
    Check if we can test the program length of a submodule.

    The program length test reads the files using get_tokens instead using the
    importer, so we need to explicitly test its handling of submodules.
    """

    options = Options(sub_module="elsewhere.submission")

    file_path = fix_syspath / (options.ref_module.replace(".", os.path.sep) + ".py")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("pass # some comments")

    file_path = fix_syspath / (options.sub_module.replace(".", os.path.sep) + ".py")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("pass # enough comments")

    the_params = [param(options)]
    built_class = build(the_params)
    built_instance = built_class(methodName="test_program_length_0")
    test_method = built_instance.test_program_length_0
    test_method()  # should not raise an error
