import os
import unittest

import pytest

from generic_grader.style.comments import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_style_comments_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_style_comments_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestCommentLength"


def test_style_comments_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_style_comments_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_comment_length_0")


# Test a file with
#   - too few comments
#   - too many comments
#   - just the right number of comments
cases = [
    {
        "submission": "pass",
        "reference": "pass # some comments",
        "result": AssertionError,
        "message": "too few comments",
        "doc_func_test": "Check if the program is well commented.",
    },
    {
        "submission": "pass # too many comments\n" * 10,
        "reference": "pass # some comments",
        "result": AssertionError,
        "message": "a lot of comments",
        "doc_func_test": "Check if the program is well commented.",
    },
    {
        "submission": "pass # enough comments",
        "reference": "pass # some comments",
        "result": "pass",
        "doc_func_test": "Check if the program is well commented.",
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

    built_class = build(
        Options(
            ref_module="reference",
            sub_module="submission",
        ),
    )
    built_instance = built_class(methodName="test_comment_length_0")
    test_method = built_instance.test_comment_length_0

    return case, test_method


def test_comment_length(case_test_method):
    """Test response of test_submitted_files function."""
    case, test_method = case_test_method
    if case["result"] == "pass":
        test_method()  # should not raise an error
    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()
        message = " ".join(str(exc_info.value).split())
        assert case["message"] in message
    assert test_method.__doc__ == case["doc_func_test"]


def test_submodule_comment_length(fix_syspath):
    """
    Check if we can test the comments of a submodule.

    The comments test opens the files to read them instead using the importer,
    so we need to explicitly test its handling of submodules.
    """

    options = Options(sub_module="elsewhere.submission")

    file_path = fix_syspath / (options.ref_module.replace(".", os.path.sep) + ".py")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("pass # some comments")

    file_path = fix_syspath / (options.sub_module.replace(".", os.path.sep) + ".py")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("pass # enough comments")

    built_class = build(options)
    built_instance = built_class(methodName="test_comment_length_0")
    test_method = built_instance.test_comment_length_0
    test_method()  # should not raise an error


# TODO add tests for the hint message
