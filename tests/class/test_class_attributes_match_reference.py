import unittest

import pytest

from generic_grader.class_.class_attributes_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_class_attributes_match_reference_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_class_attributes_match_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestClassAttributesMatchReference"


def test_class_attributes_match_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_class_attributes_match_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_class_attributes_match_reference_0")


# Cases Tested:
# 1. Passing case with same attributes
# 2. Passing case with init defined
# 3. Passing case with multiple classes defined
# 4. Wrong attribute in submission
# 5. Failing case with multiple classes defined


cases = [
    {  # Defining class with correct attributes
        "submission": "class Dummy():\n    def __init__(self):\n        pass\n    def correct_method(self):\n        pass",
        "reference": "class Dummy():\n    def __init__(self):\n        pass\n    def correct_method(self):\n        pass",
        "result": "pass",
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
            obj_name="Dummy",
        ),
        "doc_func_test_string": (
            "Check that `Dummy` class attribute names and types" " match the reference."
        ),
    },
    {  # Passing case with init defined
        "submission": "class Dummy():\n    def __init__(self):\n        pass\n    def correct_method(self):\n        pass",
        "reference": "class Dummy():\n    def __init__(self):\n        pass\n    def correct_method(self):\n        pass",
        "result": "pass",
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
            obj_name="Dummy",
            init=lambda: None,
        ),
        "doc_func_test_string": (
            "Check that `Dummy` class attribute names and types" " match the reference."
        ),
    },
    {  # Passing case with multiple classes defined
        "submission": "class Dummy1():\n    def __init__(self):\n        pass\nclass Dummy2():\n    def __init__(self):\n        pass\n    def correct_method(self):\n        pass",
        "reference": "class Dummy1():\n    def __init__(self):\n        pass\nclass Dummy2():\n    def __init__(self):\n        pass\n    def correct_method(self):\n        pass",
        "result": "pass",
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
            obj_name="Dummy2",
            init=lambda: None,
        ),
        "doc_func_test_string": (
            "Check that `Dummy2` class attribute names and types"
            " match the reference."
        ),
    },
    {  # Wrong attribute in submission
        "submission": "class Dummy():\n    def __init__(self):\n        self.wrong_attribute = 1\n    def wrong_method(self):\n        pass",
        "reference": "class Dummy():\n    def __init__(self):\n        self.correct_attribute = 1\n    def correct_method(self):\n        pass",
        "result": AssertionError,
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
            obj_name="Dummy",
            init=lambda: None,
        ),
        "doc_func_test_string": (
            "Check that `Dummy` class attribute names and types" " match the reference."
        ),
        "message": "The `Dummy` class has incorrect attributes.",
    },
    {  # Failing case with multiple classes defined
        "submission": "class Dummy1():\n    def __init__(self):\n        self.wrong_attribute = 1\n    def wrong_method(self):\n        pass\nclass Dummy2():\n    def __init__(self):\n        pass",
        "reference": "class Dummy1():\n    def __init__(self):\n        self.correct_attribute = 1\n    def correct_method(self):\n        pass\nclass Dummy2():\n    def __init__(self):\n        pass",
        "result": AssertionError,
        "options": Options(
            sub_module="submission",
            ref_module="reference",
            weight=1,
            obj_name="Dummy1",
            init=lambda: None,
        ),
        "doc_func_test_string": (
            "Check that `Dummy1` class attribute names and types"
            " match the reference."
        ),
        "message": "The `Dummy1` class has incorrect attributes.",
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
    built_instance = built_class(methodName="test_class_attributes_match_reference_0")
    test_method = built_instance.test_class_attributes_match_reference_0

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
