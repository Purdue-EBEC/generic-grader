import unittest

import pytest

from generic_grader.function.callable_not_defined import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(sub_module="submission", obj_name="test_function"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_callable_not_defined_build_class(built_class):
    """Test that the build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_callable_not_defined_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestCallableNotDefined"


def test_callable_not_defined_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_callable_not_defined_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_callable_not_defined_0")


def test_callable_not_defined_doctring(built_instance):
    """Test that the built_class has the correct doctring."""
    assert (
        built_instance.test_callable_not_defined_0.__doc__
        == "Check that `test_function` is NOT defined in module `submission`."
    )


passing_case = [
    {  # No functions defined
        "options": Options(sub_module="sub", obj_name="missing_func", weight=1),
        "file_name": "sub.py",
        "file_text": "pass",
    },
    {  # Function defined inside another function
        "options": Options(sub_module="sub", obj_name="inside_func", weight=1),
        "file_name": "sub.py",
        "file_text": "def main():\n    def inside_func():\n        pass",
    },
    {  # Different function defined
        "options": Options(sub_module="sub", obj_name="another_func", weight=1),
        "file_name": "sub.py",
        "file_text": "def main():\n    pass",
    },
    {  # Class not defined
        "options": Options(sub_module="sub", obj_name="missing_class", weight=1),
        "file_name": "sub.py",
        "file_text": "def main():\n    pass",
    },
]


@pytest.mark.parametrize("case", passing_case)
def test_callable_not_defined_passing_cases(
    case,
    fix_syspath,
):
    """Test that the class works as expected."""
    sub_file = fix_syspath / case["file_name"]
    sub_file.write_text(case["file_text"])

    built_class = build(case["options"])
    test_method = built_class(
        methodName="test_callable_not_defined_0"
    ).test_callable_not_defined_0
    test_method()
    assert test_method.__score__ == case["options"].weight


failing_cases = [
    {  # Function defined
        "options": Options(sub_module="sub", obj_name="func", weight=1),
        "file_name": "sub.py",
        "file_text": "def func():\n    pass",
        "error": "The definition of your `func` function should not be within your `sub` module.",
    },
    {  # Function defined alongside another function
        "options": Options(
            sub_module="sub", obj_name="func", weight=1, hint="This is a hint"
        ),
        "file_name": "sub.py",
        "file_text": "def func():\n    pass\ndef another_func():\n    pass",
        "error": "The definition of your `func` function should not be within your `sub` module. This is a hint",
    },
    {  # Class defined
        "options": Options(sub_module="sub", obj_name="FakeClass", weight=1),
        "file_name": "sub.py",
        "file_text": "class FakeClass:\n    pass",
        "error": "The definition of your `FakeClass` function should not be within your `sub` module.",
    },
]


@pytest.mark.skip("Need to discuss doctring")
@pytest.mark.parametrize("case", failing_cases)
def test_callable_not_defined_failing_cases(
    case,
    fix_syspath,
):
    """Test that the test fails when the function is defined."""
    sub_file = fix_syspath / case["file_name"]
    sub_file.write_text(case["file_text"])

    built_class = build(case["options"])
    test_method = built_class(
        methodName="test_callable_not_defined_0"
    ).test_callable_not_defined_0
    with pytest.raises(AssertionError) as exc_info:
        test_method()
    assert test_method.__score__ == 0
    assert case["error"] in str(exc_info.value)
