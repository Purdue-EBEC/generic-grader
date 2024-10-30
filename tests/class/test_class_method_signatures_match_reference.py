import unittest

import pytest

from generic_grader.class_.class_method_signatures_match_reference import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(obj_name="FakeClass", sub_module="fake_module"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_class_method_signatures_match_reference_build_class(built_class):
    """Test that the class_is_defined build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_class_method_signatures_match_reference_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestClassMethodSignaturesMatchReference"


def test_class_method_signatures_match_reference_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_class_method_signatures_match_reference_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_class_method_signatures_match_reference_0")


def test_class_method_signatures_match_reference_doc_func_test_string(built_instance):
    """Test that the built_class has the correct docstring."""
    assert built_instance.test_class_method_signatures_match_reference_0.__doc__ == (
        "Check the signature of each method in the `FakeClass` class."
    )


class_one_text = (
    "class FakeClass:\n"
    "    def __init__(self):\n"
    "        self.x = 1\n"
    "    def method_one(self, x: int) -> int:\n"
    "        return x\n"
    "    def method_two(self, x: int, y: int) -> int:\n"
    "        return x + y"
)

class_two_text = (
    "class FakeClass:\n"
    "    def __init__(self):\n"
    "        pass\n"
    "    def method_one(self, x: int) -> int:\n"
    "        return x\n"
    "    def method_two(self, x: int, y: int) -> int:\n"
    "        return x + y"
)

class_three_text = (
    "class FakeClass:\n"
    "    def __init__(self):\n"
    "        pass\n"
    "    def method_one(self, x: int) -> int:\n"
    "        return x*2\n"
    "    def method_two(self, x: int, y: int) -> int:\n"
    "        return 2*x + y"
)

class_four_text = (
    "class FakeClass:\n"
    "    def __init__(self):\n"
    "        pass\n"
    "    def method_one(self, x):\n"
    "        return x\n"
    "    def method_two(self, x, y):\n"
    "        return x + y"
)

class_five_text = (
    "class FakeClass:\n"
    "   def method_one(self, y: int) -> int:\n"
    "       return y\n"
    "   def method_two(self, y: int, z: int) -> int:\n"
    "       return y + z"
)

class_six_text = (
    "class FakeClass:\n"
    "   def __init__(self):\n"
    "        pass\n"
    "   def method_one(self, x):\n"
    "        return x"
)


passing_cases = [
    {  # Test that the class method signatures match the reference when they are identical.
        "sub_text": class_four_text,
        "ref_text": class_four_text,
    },
    {  # Test that it ignores different __init__ methods.
        "sub_text": class_one_text,
        "ref_text": class_two_text,
    },
    {  # Test that it ignores the return values
        "sub_text": class_one_text,
        "ref_text": class_three_text,
    },
    {  # Test that it passes with extra class methods
        "sub_text": class_four_text,
        "ref_text": class_six_text,
    },
]


@pytest.mark.parametrize("case", passing_cases)
def test_class_method_signatures_match_reference_passing(fix_syspath, case):
    """Test that the class method signatures match the reference."""
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_text"])
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_text"])
    o = Options(obj_name="FakeClass", sub_module="sub", ref_module="ref", weight=1)

    built_class = build(o)
    built_instance = built_class(
        methodName="test_class_method_signatures_match_reference_0"
    )
    test_method = built_instance.test_class_method_signatures_match_reference_0

    test_method()

    assert test_method.__score__ == o.weight


failing_cases = [
    {  # Does not ignore the type annotations
        "sub_text": class_one_text,
        "ref_text": class_four_text,
        "error_msg": (
            "\nFakeClass.method_one:\n"
            "  The signature of your `FakeClass.method_one` method differs from the\n"
            "  reference.\n\n"
            "- method_one(self, x: int) -> int\n"
            "?                   ----- -------\n"
            "+ method_one(self, x)\n\n"
            "FakeClass.method_two:\n"
            "  The signature of your `FakeClass.method_two` method differs from the\n"
            "  reference.\n\n"
            "- method_two(self, x: int, y: int) -> int\n"
            "+ method_two(self, x, y)\n"
        ),
    },
    {  # Does not ignore varible name
        "sub_text": class_one_text,
        "ref_text": class_five_text,
        "error_msg": (
            "\nFakeClass.method_one:\n"
            "  The signature of your `FakeClass.method_one` method differs from the\n"
            "  reference.\n\n"
            "- method_one(self, x: int) -> int\n"
            "?                  ^\n"
            "+ method_one(self, y: int) -> int\n"
            "?                  ^\n\n"
            "FakeClass.method_two:\n"
            "  The signature of your `FakeClass.method_two` method differs from the\n"
            "  reference.\n\n"
            "- method_two(self, x: int, y: int) -> int\n"
            "?                  ^       ^\n"
            "+ method_two(self, y: int, z: int) -> int\n"
            "?                  ^       ^\n"
        ),
    },
    {  # Test that it catches missing attributes
        "sub_text": class_six_text,
        "ref_text": class_four_text,
        "error_msg": (
            "\nFakeClass.method_two:\n"
            "  The `FakeClass` class in your `sub` module is missing a method named\n"
            "  `method_two`. Define the `method_two` method inside of your\n"
            "  `FakeClass` class using a `def` statement (e.g. `def\n"
            "  method_two(self, ...):`)."
        ),
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_class_method_signatures_match_reference_failing(fix_syspath, case):
    """Test that the class method signatures match the reference."""
    sub_file = fix_syspath / "sub.py"
    sub_file.write_text(case["sub_text"])
    ref_file = fix_syspath / "ref.py"
    ref_file.write_text(case["ref_text"])
    o = Options(obj_name="FakeClass", sub_module="sub", ref_module="ref", weight=1)
    built_class = build(o)
    built_instance = built_class(
        methodName="test_class_method_signatures_match_reference_0"
    )
    test_method = built_instance.test_class_method_signatures_match_reference_0

    with pytest.raises(AssertionError) as exc_info:
        test_method()

    assert str(exc_info.value) == case["error_msg"]

    assert test_method.__score__ == 0
