import sys
import time
import unittest
from datetime import datetime

import pytest

from generic_grader.utils.exceptions import (
    EndOfInputError,
    ExitError,
    LogLimitExceededError,
    QuitError,
    UserTimeoutError,
)
from generic_grader.utils.user import User, memory_limit, time_limit

time_limit_cases = [
    {"length": 0.5, "result": None},
    {"length": 1, "result": UserTimeoutError},
    {"length": 2, "result": UserTimeoutError},
]


@pytest.mark.parametrize("case", time_limit_cases)
def test_time_limit(case):
    """Test the time_limit function."""
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            with time_limit(1):
                time.sleep(case["length"])
    else:  #  The ideal case where no exception is raised
        with time_limit(1):
            time.sleep(case["length"])


memory_limit_cases = [
    {"limit": 1, "usage": 2, "result": MemoryError},
    {"limit": 1, "usage": 0.5, "result": None},
    {"limit": 1, "usage": 1, "result": MemoryError},
]


@pytest.mark.parametrize("case", memory_limit_cases)
def test_memory_limit(case):
    """Test the memory_limit function."""
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            with memory_limit(case["limit"]):
                " " * case["usage"] * 2**30
    else:
        with memory_limit(case["limit"]):
            " " * int(case["usage"] * 2**30)


user_log_cases = [
    {"log": "a" * 10, "limit": 10, "result": None},
    {"log": "a" * 10, "limit": 5, "result": LogLimitExceededError},
    {"log": "a" * 10, "limit": 15, "result": None},
    {"log": "a" * 10, "limit": 0, "result": None},
    {"log": "", "limit": 0, "result": None},
]


@pytest.mark.parametrize("case", user_log_cases)
def test_user_log(case):
    """Test the User class log attribute."""
    log = User.LogIO(case["limit"])
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            log.write(case["log"])
    else:
        log.write(case["log"])
        assert log.getvalue() == case["log"]


class FakeTest(unittest.TestCase):
    """Fake test class for testing User class."""

    pass


call_obj_pass = [
    {
        "module": "hello_user_1",
        "file_text": "def main():\n    print('Hello, User!')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, User!\n",
    },
    {
        "module": "input_user_1",
        "file_text": "def main():\n    name = input('What is your name? ')\n    print(f'Hello, {name}!')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": ["Jack"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "What is your name? Jack\nHello, Jack!\n",
    },
    {
        "module": "print_user_arg_1",
        "file_text": "def user_func(user):\n    print(f'Hello, {user}!')\n",
        "obj_name": "user_func",
        "call_obj": {
            "entries": "",
            "args": (["Jack"]),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, Jack!\n",
    },
    {
        "module": "print_user_kwargs_1",
        "file_text": "def user_func(user, greeting):\n    print(f'{greeting}, {user}!')\n",
        "obj_name": "user_func",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {"user": "Jack", "greeting": "Hi"},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hi, Jack!\n",
    },
    {
        "module": "hello_user_2",
        "file_text": "def main():\n    print('Hello, User!')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 13,  # The result is 13 characters long, so this should pass
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, User!\n",
    },
    {
        "module": "freeze_time_1",
        "file_text": "import datetime\n\ndef main():\n    print(datetime.datetime.now())\n\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": datetime(2021, 1, 1, 0, 0, 0),
            "debug": False,
        },
        "result": "2021-01-01 00:00:00\n",
    },
]


@pytest.fixture()
def fix_syspath():
    """
    This is the current solution to the empty string being missing
    from sys.path when running pytest."""
    old_path = sys.path.copy()
    sys.path.insert(0, "")
    yield
    sys.path = old_path


@pytest.mark.parametrize("case", call_obj_pass)
def test_passing_call_obj(case, fix_syspath, tmp_path, monkeypatch):
    """Test the User class call_obj method."""
    # Set up the test environment
    fake_file = tmp_path / f"{case['module']}.py"
    fake_file.write_text(case["file_text"])
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Create a User object
    user = User(test, case["module"], case["obj_name"])
    # Call the object
    user.call_obj(**case["call_obj"])
    # Check
    assert user.log.getvalue() == case["result"]


call_obj_fail = [
    {  # Too many entries
        "module": "hello_user_3",
        "file_text": "def main():\n    print('Hello, User!')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": ["Jack"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, User!\n",
        "error": AssertionError,
        "error_msg": "Your program ended before the user finished entering input.",
    },
    {  # Missing entry
        "module": "input_user_2",
        "file_text": "def main():\n    name = input('What is your name? ')\n    print(f'Hello, {name}!')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "What is your name? ",
        "error": EndOfInputError,
        "error_msg": "Your `main` malfunctioned when called as `main()`.",
    },
    {  # Missing argument
        "module": "print_user_arg_2",
        "file_text": "def user_func(user):\n    print(f'Hello, {user}!')\n",
        "obj_name": "user_func",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "",
        "error": TypeError,
        "error_msg": "user_func() missing 1 required positional argument: 'user'",
    },
    {  # Missing keyword argument
        "module": "print_user_kwargs_2",
        "file_text": "def user_func(user, greeting):\n    print(f'{greeting}, {user}!')\n",
        "obj_name": "user_func",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {"user": "Jack"},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "",
        "error": TypeError,
        "error_msg": "user_func() missing 1 required positional argument: 'greeting'",
    },
    {  # Log limit exceeded
        "module": "hello_user_4",
        "file_text": "def main():\n    print('Hello, User!')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 5,  # The result is 13 characters long, so this should fail
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, User!",  # No newline
        "error": LogLimitExceededError,
        "error_msg": "Your `main` malfunctioned when called as `main()`.",
    },
    {  # Exit function
        "module": "hello_user_5",
        "file_text": "def main():\n     print('Hello, User!')\n     exit()\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, User!\n",
        "error": ExitError,
        "error_msg": "Calling the `exit()` function is not allowed in this course.",
    },
    {  # Quit function
        "module": "hello_user_6",
        "file_text": "def main():\n    print('Hello, User!')\n    quit()\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "call_obj": {
            "entries": "",
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Hello, User!\n",
        "error": QuitError,
        "error_msg": "Calling the `quit()` function is not allowed in this course.",
    },
]


@pytest.mark.parametrize("case", call_obj_fail)
def test_failing_call_obj(case, fix_syspath, tmp_path, monkeypatch):
    """Test the User class call_obj method."""
    # Set up the test environment
    fake_file = tmp_path / f"{case["module"]}.py"
    fake_file.write_text(case["file_text"])
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Create a User object
    user = User(test, case["module"], case["obj_name"])
    # Call the object
    with pytest.raises(case["error"]) as exc_info:
        user.call_obj(**case["call_obj"])
    assert case["error_msg"] in exc_info.value.args[0]
    assert user.log.getvalue() == case["result"]


def test_debug_call_obj(capsys, fix_syspath, tmp_path, monkeypatch):
    """Test the debug option in the User class call_obj method."""
    # Set up the test environment
    fake_file = tmp_path / "hello_user.py"
    fake_file.write_text(
        "def main():\n    print('Hello, User!')\nif __name__ == '__main__':\n    main()\n"
    )
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Create a User object
    user = User(test, "hello_user", "main")
    # Call the object
    user.call_obj(
        entries="", args=(), kwargs={}, log_limit=0, fixed_time=False, debug=True
    )
    # Check
    captured = capsys.readouterr()
    assert captured.out == "Hello, User!\n\n"
    assert user.log.getvalue() == "Hello, User!\n"
    assert captured.err == ""


# TODO Add decimals, large numbers with commas, negative numbers, floats, and scientific notation
@pytest.fixture(scope="function")
def complete_user(fix_syspath, tmp_path, monkeypatch):
    """Create a User object for testing."""
    fake_file = tmp_path / "add_numbers.py"
    fake_file.write_text(
        "def add_numbers():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n"
    )
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = User(test, "add_numbers", "add_numbers")
    user.call_obj(
        entries=["1", "10"],
        args=(),
        kwargs={},
        log_limit=0,
        fixed_time=False,
        debug=False,
    )
    return user


def test_read_log_lines(complete_user):
    """Test the User class read_log_lines method."""
    user = complete_user
    assert user.read_log_lines() == [
        "Enter the first number: 1\n",
        "Enter the second number: 10\n",
        "1 + 10 = 11\n",
    ]


def test_read_log_line(complete_user):
    """Test the User class read_log_line method."""
    user = complete_user
    assert user.read_log_line() == "Enter the first number: 1\n"
    assert user.read_log_line(line_n=2) == "Enter the second number: 10\n"
    assert user.read_log_line(line_n=3) == "1 + 10 = 11\n"
    with pytest.raises(IndexError) as exc_info:
        user.read_log_line(line_n=4)
    assert "Looking for line 4, but output only has 3 lines" in exc_info.value.args[0]


def test_read_log(complete_user):
    """Test the User class read_log method."""
    user = complete_user
    assert (
        user.read_log()
        == "Enter the first number: 1\nEnter the second number: 10\n1 + 10 = 11\n"
    )


def test_format_log(complete_user, fix_syspath, tmp_path, monkeypatch):
    """Test the User class format_log method."""
    log = (
        "\n\nline |Input/Output Log:\n"
        + "-" * 70
        + "\n"
        + "   1 |Enter the first number: 1\n"
        + "   2 |Enter the second number: 10\n"
        + "   3 |1 + 10 = 11\n"
    )
    assert complete_user.format_log() == log
    fake_file = tmp_path / "nothing.py"
    fake_file.write_text("def nothing():\n    pass\n")
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = User(test, "nothing", "nothing")
    assert user.format_log() == ""


def test_get_values(complete_user):
    """Test the User class get_values method."""
    user = complete_user
    assert user.get_values(line_n=1) == [1]
    assert user.get_values(line_n=2) == [10]
    assert user.get_values(line_n=3) == [1, 10, 11]
    with pytest.raises(IndexError) as exc_info:
        user.get_values(line_n=4)
    assert "Looking for line 4, but output only has 3 lines" in exc_info.value.args[0]


def test_get_value(complete_user):
    """Test the User class get_value method."""
    user = complete_user
    assert user.get_value(line_n=1) == 1
    assert user.get_value(line_n=2) == 10
    assert user.get_value(line_n=3, value_n=1) == 1
    assert user.get_value(line_n=3, value_n=2) == 10
    assert user.get_value(line_n=3, value_n=3) == 11
    with pytest.raises(IndexError) as exc_info:
        user.get_value(line_n=3, value_n=4)
    assert (
        "Looking for the 4th value in the 3rd output line, but only found 3"
        in exc_info.value.args[0]
    )
