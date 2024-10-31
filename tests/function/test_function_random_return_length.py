import unittest

import pytest

from generic_grader.function.function_random_return_length import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(expected_set={1, 2, 3, 4}))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_random_func_return_length_build_class(built_class):
    """Test that the random_func_return_length build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_random_func_return_length_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFuncRandomReturnLength"


def test_random_func_return_length_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_random_func_return_length_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_return_length_0")


def test_random_func_return_length_doc_func_test_string(built_instance):
    """Test that the built_class has the correct docstring."""
    assert built_instance.test_return_length_0.__doc__ == (
        "Check the lengths of value(s) returned from your `.main`"
        " function when called as `main()` matches the expected lengths."
    )


func_one = """
import random\n
def func():\n
   return 'a' * random.randint(1, 5)\n
"""

func_two = """
import random\n
def func():\n
   return 'a' * random.randint(2, 5)\n
"""

func_three = """
import random\n
def func():\n
   return 'a' * random.randint(1, 4)\n
"""

func_four = """
import random\n
def func():\n
   return 'b' * random.randint(1, 5)\n
"""

func_five = """
import random\n
def func():\n
   return 'a' * random.randint(1, 6)\n
"""

func_six = """
def func():\n
   return 'a'\n
"""

func_seven = """
def func():\n
   pass\n
"""

passing_cases = [
    {
        "func": func_one,
        "expected": {1, 2, 3, 4, 5},
    },
    {
        "func": func_two,
        "expected": {2, 3, 4, 5},
    },
    {
        "func": func_three,
        "expected": {1, 2, 3, 4},
    },
    {
        "func": func_four,
        "expected": {1, 2, 3, 4, 5},
    },
    {
        "func": func_five,
        "expected": {1, 2, 3, 4, 5, 6},
    },
    {
        "func": func_six,
        "expected": {1},
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_random_func_return_length_passing_cases(fix_syspath, case):
    """Test that the test passes for the passing cases."""
    file = fix_syspath / "sub.py"
    file.write_text(case["func"])
    o = Options(
        expected_set=case["expected"], weight=1, sub_module="sub", obj_name="func"
    )
    built_class = build(o)
    test_instance = built_class(methodName="test_return_length_0")
    test_method = test_instance.test_return_length_0

    test_method()

    assert test_method.__score__ == o.weight


failing_cases = [
    {  # Got 1-5
        "func": func_one,
        "expected": {1, 2, 3, 4},
        "msg": (
            "Items in the first set but not the second:\n5",
            "  The lengths of values returned from your `sub.func` function when\n  called as `func()` did not match the expected lengths.",
        ),
    },
    {  # Got 2-5
        "func": func_two,
        "expected": {1, 2, 3, 4},
        "msg": (
            "Items in the first set but not the second:\n5",
            "  The lengths of values returned from your `sub.func` function when\n  "
            "called as `func()` did not match the expected lengths.",
        ),
    },
    {  # Got 1-4
        "func": func_three,
        "expected": {1, 2, 3, 4, 5},
        "msg": (
            "Items in the second set but not the first:\n5",
            "  The lengths of values returned from your `sub.func` function when\n  called as `func()` did not match the expected lengths.",
        ),
    },
    {  # Got 1-5
        "func": func_four,
        "expected": {1, 2, 3, 4},
        "msg": (
            "Items in the first set but not the second:\n5",
            "  The lengths of values returned from your `sub.func` function when\n  called as `func()` did not match the expected lengths.",
        ),
    },
    {  # Got 1-6
        "func": func_five,
        "expected": {1, 2, 3, 4, 5},
        "msg": (
            "Items in the first set but not the second:\n6",
            "  The lengths of values returned from your `sub.func` function when\n"
            "  called as `func()` did not match the expected lengths.\n\n",
        ),
    },
    {  # Got 1
        "func": func_six,
        "expected": {1, 2},
        "msg": (
            "Items in the second set but not the first:",
            "Hint:\n"
            "  The lengths of values returned from your `sub.func` function when\n"
            "  called as `func()` did not match the expected lengths.\n\n",
        ),
    },
    {  # Got NoneType
        "func": func_seven,
        "expected": {1},
        "msg": (
            "Hint:\n"
            "  Your `sub.func` function when called as `func()` did not return a\n"
            "  value that has a length. Make sure your function returns a value\n"
            "  that supports the `len()` function.\n"
        ),
        "init": lambda *args, **kwargs: print("init has run"),
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_random_func_return_length_failing_cases(fix_syspath, case, capsys):
    """Test that the test fails for the failing cases."""
    file = fix_syspath / "sub.py"
    file.write_text(case["func"])
    init = case.get("init", None)
    if init:
        o = Options(
            expected_set=case["expected"],
            weight=1,
            sub_module="sub",
            obj_name="func",
            init=case["init"],
        )
    else:
        o = Options(
            expected_set=case["expected"], weight=1, sub_module="sub", obj_name="func"
        )

    built_class = build(o)
    test_instance = built_class(methodName="test_return_length_0")
    test_method = test_instance.test_return_length_0
    with pytest.raises(AssertionError) as exc_info:
        test_method()

    if init:
        assert capsys.readouterr().out == "init has run\n"
    for msg_str in case["msg"]:
        assert msg_str in str(exc_info.value)
    assert test_method.__score__ == 0
