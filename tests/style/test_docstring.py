import unittest

import pytest
from parameterized import param

from generic_grader.style.docstring import build
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


def test_style_docstring_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_style_docstring_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestDocstring"


def test_style_docstring_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_style_comments_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_docstring_0")
    assert hasattr(built_instance, "test_docstring_1")
    assert hasattr(built_instance, "test_docstring_2")
    assert hasattr(built_instance, "test_docstring_3")
    assert hasattr(built_instance, "test_docstring_4")
    assert hasattr(built_instance, "test_docstring_5")
    assert hasattr(built_instance, "test_docstring_6")


# Test a file with
#   - Module level docstring absent
#   - Author absent
#   - Assignment name absent
#   - Assignment date absent
#   - Description too short* - yet to add
#   - Description too long* - yet to add
#   - Contributors absent
#   - Academic Integrity statement absent
#   - All components present

cases = [
    {
        "submission": "None",
        "reference": "pass module level docstring",
        "result": AssertionError,
        "message": "Module level docstring not found",
    },
    {
        "submission": "None",
        "reference": "pass some Author",
        "result": AssertionError,
        "message": "Author name is absent",
    },
    {
        "submission": "None",
        "reference": "pass some Assignment name",
        "result": AssertionError,
        "message": "Assignment name is absent",
    },
    {
        "submission": "None",
        "reference": "pass some Date",
        "result": AssertionError,
        "message": "Assignment date is absent",
    },
    {
        "submission": "None",
        "reference": "pass some Author",
        "result": AssertionError,
        "message": "Author name is absent",
    },
    {
        "submission": "None",
        "reference": "pass some contributors",
        "result": AssertionError,
        "message": "Contributors are absent",
    },
    {
        "submission": "None",
        "reference": "pass Academic Integrity statement",
        "result": AssertionError,
        "message": "Contributors are absent",
    },
    {
        "submission": "pass completed docstring",
        "reference": "pass complete docstring",
        "result": "pass",
    },
]
# Make a table for all possible tests

# Make the value of submission key to an entire submission
# Try taking thing in an out to test if it works


@pytest.fixture(params=cases)
def case_test_method(request, tmp_path, monkeypatch):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    file_path = tmp_path / "submission.py"
    file_path.write_text(case["submission"])
    file_path = tmp_path / "reference.py"
    file_path.write_text(case["reference"])
    monkeypatch.chdir(tmp_path)

    the_params = [
        param(
            Options(
                sub_module="submission",
                ref_module="reference",
            ),
        )
    ]
    built_class = build(the_params)
    built_instance = built_class()
    test_method = built_instance.test_docstring

    return case, test_method


def test_docstring(case_test_method):
    """Test docstring of test_submitted_files function."""
    case, test_method = case_test_method
    if case["result"] == "pass":
        test_method()  # should not raise an error
    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
