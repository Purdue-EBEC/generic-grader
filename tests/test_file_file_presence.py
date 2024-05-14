import unittest

import pytest
from parameterized import param

from generic_grader.file.file_presence import build
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


def test_file_presence_build_class(built_class):
    """Test that the file presence build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_file_presence_build_class_name(built_class):
    """Test that the built_class has the correct name."""
    assert built_class.__name__ == "TestFilePresence"


def test_file_presence_built_instance_type(built_instance):
    """Test that the built_class returns instances of unittest.TestCase."""
    assert isinstance(built_instance, unittest.TestCase)


def test_file_presence_instance_has_test_method(built_instance):
    """Test that instances of the built_class have test method."""
    assert hasattr(built_instance, "test_submitted_files_0")


# This will break when the test is updated to fail when no files are present.


def test_file_presence_method_none(built_instance):
    """Test the test_submitted_files method returns None."""
    assert built_instance.test_submitted_files_0() is None


# |        present | required | ignored | expected result                             |
# |---------------:|---------:|--------:|:--------------------------------------------|
# |              - |        - |       - | raises error, at least one file is required |
# |            foo |      foo |       - | pass: required file is present              |
# |            foo |      bar |       - | fail: required file is missing              |
# |      foo, foot |      foo |       - | fail: extra file matching pattern present   |
# |      foo, foot |      foo |    foot | pass: the extra file is ignored             |
# |       foo, bar | foo, bar |       - | pass: both required files are present       |
# |            bar | foo, bar |       - | fail: first required file is missing        |
# |            foo | foo, bar |       - | fail: second required file is missing       |
# |              - | foo, bar |       - | fail: both required files are missing       |
# | foo, bar, barf | foo, bar |       - | fail: an extra file is present              |
# | foo, bar, barf | foo, bar |    barf | pass: the extra file is ignored             |
#
# Consider adding a test with two extra files.
# | foo, foot, bar, barf | foo, bar |       - | fail: an extra file is present        |

cases = [
    {
        "present": (),
        "required": (),
        "ignored": (),
        # TODO: This should fail when no files are present.
        # "result": AssertionError,
        # "message": "Submissions must contain at least one file.",
        "result": "pass",
        "message": "Found all required files.",
    },
    {
        "present": ("foo_login.py",),
        "required": ("foo*.py",),
        "ignored": (),
        "result": "pass",
        "message": "Found all required files.",
    },
    {
        "present": ("foo_login.py",),
        "required": ("bar*.py",),
        "ignored": (),
        "result": AssertionError,
        "message": 'Cannot find any files matching the pattern "bar*.py".',
    },
    {
        "present": ("foo_login.py", "foot_login.py"),
        "required": ("foo*.py",),
        "ignored": (),
        "result": AssertionError,
        "message": 'too many files matching the pattern "foo*.py".',
    },
    {
        "present": ("foo_login.py", "foot_login.py"),
        "required": ("foo*.py",),
        "ignored": ("foot*.py",),
        "result": "pass",
        "message": "Found all required files.",
    },
    {
        "present": ("foo_login.py", "bar_login.py"),
        "required": ("foo*.py", "bar*.py"),
        "ignored": (),
        "result": "pass",
        "message": "Found all required files.",
    },
    {
        "present": ("bar_login.py",),
        "required": ("foo*.py", "bar*.py"),
        "ignored": (),
        "result": AssertionError,
        "message": 'Cannot find any files matching the pattern "foo*.py".',
    },
    {
        "present": ("foo_login.py",),
        "required": ("foo*.py", "bar*.py"),
        "ignored": (),
        "result": AssertionError,
        "message": 'Cannot find any files matching the pattern "bar*.py".',
    },
    # { # TODO this should have a better error message.
    #    "present": (),
    #    "required": ("foo*.py", "bar*.py"),
    #    "ignored": (),
    #    "result": AssertionError,
    #    "message": 'Cannot find files matching the patterns "foo*.py", or "bar*.py".',
    # },
    {
        "present": ("foo_login.py", "bar_login.py", "barf_login.py"),
        "required": ("foo*.py", "bar*.py"),
        "ignored": (),
        "result": AssertionError,
        "message": 'too many files matching the pattern "bar*.py".',
    },
    {
        "present": ("foo_login.py", "bar_login.py", "barf_login.py"),
        "required": ("foo*.py", "bar*.py"),
        "ignored": ("barf*.py",),
        "result": "pass",
        "message": "Found all required files.",
    },
    {
        "present": ("foo.py",),
        "required": ("foo*.py",),
        "ignored": (),
        "result": AssertionError,
        "message": '"foo.py" does not meet this exercise\'s file naming requirements',
    },
]


@pytest.fixture(params=cases)
def case_test_method(request, tmp_path, monkeypatch):
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
                ignored_files=case["ignored"],
            ),
        )
    ]
    built_class = build(the_params)
    built_instance = built_class()
    test_method = built_instance.test_submitted_files_0

    return case, test_method


def test_file_presence(case_test_method, capsys):
    """Test response of test_submitted_files function."""
    case, test_method = case_test_method
    if case["result"] == "pass":
        test_method()
        assert case["message"] in capsys.readouterr().out.rstrip()
    else:
        error = case["result"]
        with pytest.raises(error) as exc_info:
            test_method()
        assert case["message"] in " ".join(str(exc_info.value).split())
