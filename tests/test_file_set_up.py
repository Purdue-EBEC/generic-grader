import unittest
from pathlib import Path

import pytest
from parameterized import param

from generic_grader.file.file_set_up import build
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


def test_file_set_up_build_class(built_class):
    """Test that the file presence build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_file_set_up_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFileSetUp"


def test_file_set_up_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_file_set_up_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_file_set_up_0")


# |        present | required | expected result                             |
# |---------------:|---------:|:--------------------------------------------|
# |          foo_l |      foo | symlink foo_login to foo.py                 |
# |          bar_l |      foo | no action                                   |
# |  foo_l, foot_l |      foo | fail: extra file matching pattern present   |
# |      foo, foot |      foo | pass: the extra file is ignored             |
# |       foo, bar | foo, bar | pass: both required files are present       |
# |            bar | foo, bar | fail: first required file is missing        |
# |            foo | foo, bar | fail: second required file is missing       |
# |              - | foo, bar | fail: both required files are missing       |
# | foo, bar, barf | foo, bar | fail: an extra file is present              |
# | foo, bar, barf | foo, bar | pass: the extra file is ignored             |
#

set_up_cases = [
    {
        "present": ("foo_login.py",),
        "required": ("foo*.py",),
    },
    # TODO add remaining cases
]


@pytest.fixture(params=set_up_cases)
def set_up_case_test_method(request, tmp_path, monkeypatch):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    for file_name in case["present"]:
        file_path = tmp_path / file_name
        file_path.write_text("")
    monkeypatch.chdir(tmp_path)

    params = [
        param(
            Options(
                required_files=case["required"],
            ),
        )
    ]
    built_class = build(params)
    built_instance = built_class()
    test_method = built_instance.test_file_set_up_0

    return case, test_method


def test_file_setup(set_up_case_test_method):
    """Test that the file setup function returns a class."""
    case, test_method = set_up_case_test_method
    required_patterns = case["required"]
    test_method()
    for pattern in required_patterns:
        assert Path(pattern.replace("*", "")).is_symlink()
