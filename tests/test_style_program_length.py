import unittest

import pytest
from parameterized import param

from generic_grader.style.program_length import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    o = Options()
    params = param(o)
    return build(params)


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
def case_test_method(request, tmp_path, monkeypatch):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = tmp_path / "submission.py"
    file_path.write_text(case["submission"])
    file_path = tmp_path / "reference.py"
    file_path.write_text(case["reference"])
    monkeypatch.chdir(tmp_path)

    params = [
        param(
            Options(
                sub_module="submission",
                ref_module="reference",
                weight=case["weight"],
            ),
        )
    ]
    built_class = build(params)
    built_instance = built_class(methodName="test_program_length_0")
    test_method = built_instance.test_program_length_0

    return case, built_instance, test_method


def test_program_length(case_test_method):
    """Test response of test_submitted_files function."""
    case, built_instance, test_method = case_test_method

    if case["result"] == "pass":
        built_instance.run()
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

        # We must call cleanups manually since we called the test method
        # directly instead of using the instance's run() method.
        built_instance.doCleanups()
        assert test_method.__score__ == case["score"]
