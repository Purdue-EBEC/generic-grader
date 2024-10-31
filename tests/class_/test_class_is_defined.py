import unittest

import pytest

from generic_grader.class_.class_is_defined import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    return build(Options(obj_name="FakeClass", sub_module="fake_module"))


@pytest.fixture()
def built_instance(built_class):
    """Provide an instance of the built class."""
    return built_class()


def test_class_is_defined_build_class(built_class):
    """Test that the class_is_defined build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_class_is_defined_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestClassIsDefined"


def test_class_is_defined_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_class_is_defined_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_class_is_defined_0")


def test_class_is_defined_doc_func_test_string(built_instance):
    """Test that the built_class has the correct docstring."""
    assert built_instance.test_class_is_defined_0.__doc__ == (
        "Check that class `FakeClass` is defined in module `fake_module`."
    )


class_text_1 = "class FakeClass:\n" "    pass\n"

class_text_2 = "import unittest\n" "class FakeClass(unittest.TestCase):\n" "    pass\n"

class_text_3 = (
    "class FakeClass:\n" "    def __init__(self):\n" "        self.fake_attr = 1\n"
)

class_text_4 = "class FakeClass:\n" "    def fake_method(self):\n" "        return 1\n"

class_text_5 = "def fake_function():\n" "    pass\n"

class_text_6 = "def FakeClass():\n" "    pass\n"

class_text_7 = "def main():\n" "    class FakeClass:\n" "        pass\n"


passing_cases = [
    class_text_1,
    class_text_2,
    class_text_3,
    class_text_4,
]


@pytest.mark.parametrize("class_text", passing_cases)
def test_class_is_defined_passing(class_text, fix_syspath):
    """Test that the class is defined in the module."""
    o = Options(obj_name="FakeClass", sub_module="fake_module", weight=1)
    sub_file = fix_syspath / "fake_module.py"
    sub_file.write_text(class_text)
    built_class = build(o)
    built_instance = built_class(methodName="test_class_is_defined_0")
    test_method = built_instance.test_class_is_defined_0

    test_method()

    assert test_method.__score__ == o.weight


error_1 = (
    "\n  Unable to import `FakeClass`.\n\n"
    "Hint:\n"
    "  Define `FakeClass` in your `fake_module` module, and make sure its\n"
    "  definition is not inside of any other block."
)

error_2 = (
    "\n  The object `FakeClass` is not a class.\n\n"
    "Hint:\n"
    "  Define the `FakeClass` class in your `fake_module` module using a\n"
    "  `class` statement (e.g. `class FakeClass():`).  Also, make sure your\n"
    "  class definition is not inside of any other block."
)

failing_cases = [
    {
        "class_text": class_text_5,
        "error": AttributeError,
        "error_message": error_1,
        "options": Options(obj_name="FakeClass", sub_module="fake_module", weight=1),
    },
    {
        "class_text": class_text_6,
        "error": AssertionError,
        "error_message": error_2,
        "options": Options(obj_name="FakeClass", sub_module="fake_module", weight=1),
    },
    {
        "class_text": class_text_7,
        "error": AttributeError,
        "error_message": error_1,
        "options": Options(
            obj_name="FakeClass",
            sub_module="fake_module",
            weight=1,
            init=lambda *args: print("fake init"),
        ),
    },
]


@pytest.mark.parametrize("case", failing_cases)
def test_class_is_defined_failing(case, fix_syspath, capsys):
    """Test that the class is not defined in the module."""
    o = case["options"]
    sub_file = fix_syspath / "fake_module.py"
    sub_file.write_text(case["class_text"])
    built_class = build(o)
    built_instance = built_class(methodName="test_class_is_defined_0")
    test_method = built_instance.test_class_is_defined_0

    with pytest.raises(case["error"]) as exc_info:
        test_method()

    if o.init:
        assert "fake init" == capsys.readouterr().out.strip()

    assert case["error_message"] == str(exc_info.value)

    assert test_method.__score__ == 0
