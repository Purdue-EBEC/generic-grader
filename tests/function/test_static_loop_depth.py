import unittest

import pytest

from generic_grader.function.static_loop_depth import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options())


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_static_loop_depth_build_class(built_class):
    """Test that the style comments build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_static_loop_depth_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestStaticLoopDepth"


def test_static_loop_depth_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_static_loop_depth_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_static_loop_depth_0")


# Cases Tested:
# 1. Equal to required depth with default depth
# 2. Equal required depth with expected_minimim_depth = 2
# 3. More than required depth
# 4. Less than required depth
# 5. Less than required depth with expected_minimim_depth = 2


cases = [
    {  # Equal to required depth with default depth
        "submission": (
            "def main():\n" "    for i in range(1):\n" "       print('exact depth')"
        ),
        "reference": (
            "def main():\n" "    for i in range(1):\n" "       print(f'exact depth')"
        ),
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the loop depth"
            " in your `main` function when called as `main()`"
            " meets the minimum requirements."
        ),
    },
    {  # Equal required depth with expected_minimim_depth = 2 (> 1)
        "submission": (
            "def main():\n"
            "    for i in range(1):\n"
            "       for j in range(1):\n"
            "           print('exact depth')"
        ),
        "reference": (
            "def main():\n"
            "    for i in range(1):\n"
            "       for j in range(1):\n"
            "           print(f'exact depth')"
        ),
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            expected_minimum_depth=2,
        ),
        "doc_func_test_string": (
            "Check that the loop depth"
            " in your `main` function when called as `main()`"
            " meets the minimum requirements."
        ),
    },
    {  # More than required depth
        "submission": (
            "def main():\n"
            "    for i in range(1):\n"
            "       while True:\n"
            "           print('more than required depth')"
        ),
        "reference": (
            "def main():\n" "    for i in range(1):\n" "       print(f'exact depth')"
        ),
        "result": "pass",
        "score": 1,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the loop depth"
            " in your `main` function when called as `main()`"
            " meets the minimum requirements."
        ),
    },
    {  # Less than required depth
        "submission": ("def main():\n" "    pass"),
        "reference": (
            "def main():\n" "    for i in range(1):\n" "       print(f'exact depth')"
        ),
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
        ),
        "doc_func_test_string": (
            "Check that the loop depth"
            " in your `main` function when called as `main()`"
            " meets the minimum requirements."
        ),
        "message": "This assignment requires the use of at least one loop",
    },
    {  # Less than required depth with expected_minimim_depth = 2 (> 1)
        "submission": (
            "def main():\n"
            "    for i in range(1):\n"
            "       print('less than required depth')"
        ),
        "reference": (
            "def main():\n"
            "    for i in range(1):\n"
            "       for j in range(1):\n"
            "           print(f'exact depth')"
        ),
        "result": AssertionError,
        "score": 0,
        "options": Options(
            obj_name="main",
            sub_module="submission",
            ref_module="reference",
            weight=1,
            expected_minimum_depth=2,
        ),
        "doc_func_test_string": (
            "Check that the loop depth"
            " in your `main` function when called as `main()`"
            " meets the minimum requirements."
        ),
        "message": "This assignment requires the use of nested loops",
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
    built_instance = built_class(methodName="test_static_loop_depth_0")
    test_method = built_instance.test_static_loop_depth_0

    return case, test_method


def test_static_loop_depth(case_test_method):
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
