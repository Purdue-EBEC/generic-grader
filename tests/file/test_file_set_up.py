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
    the_params = param(o)
    return build(the_params)


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


# |          present |   required | ignored | expected result                          |
# |-----------------:|-----------:|--------:|:-----------------------------------------|
# |              foo |        foo |       - | no action (file already exists)          |
# |              foo |       foo* |       - | no action (file matching pattern exists) |
# |             foo_ |       foo* |       - | symlink foo_login to foo.py              |
# |             bar_ |       foo* |       - | no action (missing source file)          |
# |       foo_, foot |       foo* |       - | no action (ambiguous request)            |
# |       foo_, foot |       foo* |    foot | symlink foo_login to foo.py              |
# |       foo_, bar_ | foo*, bar* |       - | symlink both files                       |
# |             bar_ | foo*, bar* |       - | symlink bar_login to bar.py              |
# |             foo_ | foo*, bar* |       - | symlink foo_login to foo.py              |
# |                - | foo*, bar* |       - | no action (missing source files)         |
# | foo_, bar_, barf | foo*, bar* |       - | symlink foo_login to foo.py              |
# | foo_, bar_, barf | foo*, bar* |    barf | symlink to foo.py and bar.py             |

set_up_cases = [
    {
        "present": ("foo.py",),
        "required": ("foo.py",),
        "expected_symlinks": set(),
    },
    {
        "present": ("foo.py",),
        "required": ("foo*.py",),
        "expected_symlinks": set(),
    },
    {
        "present": ("foo_login.py",),
        "required": ("foo*.py",),
        "expected_symlinks": {"foo.py"},
    },
    {
        "present": ("bar_login.py",),
        "required": ("foo*.py",),
        "expected_symlinks": set(),
    },
    {
        "present": (
            "foo_login.py",
            "foot.py",
        ),
        "required": ("foo*.py",),
        "expected_symlinks": set(),
    },
    {
        "present": (
            "foo_login.py",
            "foot.py",
        ),
        "required": ("foo*.py",),
        "ignored": ("foot.py",),
        "expected_symlinks": {"foo.py"},
    },
    {
        "present": (
            "foo_login.py",
            "bar_login.py",
        ),
        "required": (
            "foo*.py",
            "bar*.py",
        ),
        "expected_symlinks": {"foo.py", "bar.py"},
    },
    {
        "present": ("bar_login.py",),
        "required": (
            "foo*.py",
            "bar*.py",
        ),
        "expected_symlinks": {"bar.py"},
    },
    {
        "present": ("foo_login.py",),
        "required": (
            "foo*.py",
            "bar*.py",
        ),
        "expected_symlinks": {"foo.py"},
    },
    {
        "present": tuple(),
        "required": (
            "foo*.py",
            "bar*.py",
        ),
        "expected_symlinks": set(),
    },
    {
        "present": (
            "foo_login.py",
            "bar_login.py",
            "barf.py",
        ),
        "required": (
            "foo*.py",
            "bar*.py",
        ),
        "expected_symlinks": {"foo.py"},
    },
    {
        "present": (
            "foo_login.py",
            "bar_login.py",
            "barf.py",
        ),
        "required": (
            "foo*.py",
            "bar*.py",
        ),
        "ignored": ("barf.py",),
        "expected_symlinks": {"foo.py", "bar.py"},
    },
]


@pytest.fixture(params=set_up_cases)
def set_up_case_test_method(request, tmp_path, monkeypatch):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    for file_name in case["present"]:
        file_path = tmp_path / file_name
        file_path.write_text("")
    monkeypatch.chdir(tmp_path)

    the_params = [
        param(
            Options(
                required_files=case["required"],
                ignored_files=case.get("ignored", tuple()),
            ),
        )
    ]
    built_class = build(the_params)
    built_instance = built_class()
    test_method = built_instance.test_file_set_up_0

    return case, test_method


def test_file_setup(set_up_case_test_method):
    """Test that the file setup function returns a class."""
    case, test_method = set_up_case_test_method
    test_method()

    # Check for the expected symlinks.
    actual_symlinks = {p.name for p in Path().iterdir() if p.is_symlink()}
    assert actual_symlinks == case["expected_symlinks"]
