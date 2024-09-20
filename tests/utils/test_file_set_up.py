from pathlib import Path

import pytest

from generic_grader.utils.file_set_up import file_set_up
from generic_grader.utils.options import Options

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
def set_up_case_test_method(request, fix_syspath):
    """Arrange submission directory, and parameterized test function."""
    case = request.param
    for file_name in case["present"]:
        file_path = fix_syspath / file_name
        file_path.write_text("")
    o = Options(
        required_files=case["required"], ignored_files=case.get("ignored", tuple())
    )
    return case, o


def test_file_setup(set_up_case_test_method):
    case, o = set_up_case_test_method

    with file_set_up(o):
        actual_symlinks = {p.name for p in Path().iterdir() if p.is_symlink()}
        assert actual_symlinks == case["expected_symlinks"]
    removed_symlinks = {p.name for p in Path().iterdir() if p.is_symlink()}
    assert not removed_symlinks


def test_init(capsys):
    """Test that an init gets run"""

    def init():
        print("init")

    o = Options(init=init)
    with file_set_up(o):
        pass
    captured = capsys.readouterr()
    assert captured.out == "init\n"
