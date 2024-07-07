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
    {"usage": 0.5, "result": None},
    {"usage": 1, "result": MemoryError},
    {"usage": 2, "result": MemoryError},
]


@pytest.mark.parametrize("case", memory_limit_cases)
def test_memory_limit(case):
    """Test the memory_limit function."""
    if case["result"] is not None:
        with pytest.raises(case["result"]):
            with memory_limit(1):
                " " * int(case["usage"] * 2**30)
    else:
        with memory_limit(1):
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
        "file_text": "def main():\n    print('Hello, User!')\n",
        "obj_name": "main",
        "patches": None,
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
        "file_text": "def main():\n    name = input('What is your name? ')\n    print(f'Hello, {name}!')\n",
        "obj_name": "main",
        "patches": None,
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
        "patches": None,
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
        "patches": None,
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
        "patches": None,
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
        "patches": None,
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
    {
        "module": "int_patch_1",
        "file_text": "def main():\n    x = input('Enter a string: ')\n    print(f'{x} * 2 = {int(x)}')\nif __name__ == '__main__':\n    main()\n",
        "obj_name": "main",
        "patches": [{"args": ["builtins.int", lambda x: x * 2]}],
        "call_obj": {
            "entries": ["100"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "result": "Enter a string: 100\n100 * 2 = 100100\n",
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
    print(case["patches"])
    user = User(test, case["module"], case["obj_name"], case["patches"])
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
    },
]


@pytest.mark.parametrize("case", call_obj_fail)
def test_failing_call_obj(case, fix_syspath, tmp_path, monkeypatch):
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
    with pytest.raises(case["error"]):
        user.call_obj(**case["call_obj"])
    assert user.log.getvalue() == case["result"]


def test_debug_call_obj(capsys, fix_syspath, tmp_path, monkeypatch):
    """Test the debug option in the User class call_obj method."""
    # Set up the test environment
    fake_file = tmp_path / "hello_user.py"
    fake_file.write_text("def main():\n    print('Hello, User!')\n")
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


complete_user_cases = [
    {
        "module": "add_numbers_1",
        "file_text": "def add_number():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n",
        "obj_name": "add_number",
        "call_obj": {
            "entries": ["1", "10"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "full_log": "Enter the first number: 1\nEnter the second number: 10\n1 + 10 = 11\n",
        "log_lines": [
            "Enter the first number: 1\n",
            "Enter the second number: 10\n",
            "1 + 10 = 11\n",
        ],
        "formatted_log": "\n\nline |Input/Output Log:\n"
        + "-" * 70
        + "\n"
        + "   1 |Enter the first number: 1\n"
        + "   2 |Enter the second number: 10\n"
        + "   3 |1 + 10 = 11\n",
        "values": [
            [1],
            [10],
            [1, 10, 11],
        ],
    },
    {
        "module": "add_decimals_1",
        "file_text": "def add_decimal():\n    num1 = float(input('Enter the first number: '))\n    num2 = float(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n",
        "obj_name": "add_decimal",
        "call_obj": {
            "entries": ["1.1", "10.1"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "full_log": "Enter the first number: 1.1\nEnter the second number: 10.1\n1.1 + 10.1 = 11.2\n",
        "log_lines": [
            "Enter the first number: 1.1\n",
            "Enter the second number: 10.1\n",
            "1.1 + 10.1 = 11.2\n",
        ],
        "formatted_log": "\n\nline |Input/Output Log:\n"
        + "-" * 70
        + "\n"
        + "   1 |Enter the first number: 1.1\n"
        + "   2 |Enter the second number: 10.1\n"
        + "   3 |1.1 + 10.1 = 11.2\n",
        "values": [
            [1.1],
            [10.1],
            [1.1, 10.1, 11.2],
        ],
    },
    {
        "module": "add_negative_1",
        "file_text": "def add_negative():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n",
        "obj_name": "add_negative",
        "call_obj": {
            "entries": ["-1", "-10"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "full_log": "Enter the first number: -1\nEnter the second number: -10\n-1 + -10 = -11\n",
        "log_lines": [
            "Enter the first number: -1\n",
            "Enter the second number: -10\n",
            "-1 + -10 = -11\n",
        ],
        "formatted_log": "\n\nline |Input/Output Log:\n"
        + "-" * 70
        + "\n"
        + "   1 |Enter the first number: -1\n"
        + "   2 |Enter the second number: -10\n"
        + "   3 |-1 + -10 = -11\n",
        "values": [
            [-1],
            [-10],
            [-1, -10, -11],
        ],
    },
    {
        "module": "multiply_large_1",
        "file_text": "def multiply_large():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} * {num2} = {(num1 * num2):,}')",
        "obj_name": "multiply_large",
        "call_obj": {
            "entries": ["100", "1000000"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "full_log": "Enter the first number: 100\nEnter the second number: 1000000\n100 * 1000000 = 100,000,000\n",
        "log_lines": [
            "Enter the first number: 100\n",
            "Enter the second number: 1000000\n",
            "100 * 1000000 = 100,000,000\n",
        ],
        "formatted_log": "\n\nline |Input/Output Log:\n"
        + "-" * 70
        + "\n"
        + "   1 |Enter the first number: 100\n"
        + "   2 |Enter the second number: 1000000\n"
        + "   3 |100 * 1000000 = 100,000,000\n",
        "values": [
            [100],
            [1000000],
            [100, 1000000, 100000000],
        ],
    },
    {
        "module": "multiply_large_2",
        "file_text": "def multiply_large():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} * {num2} = {(num1 * num2):.2e}')",
        "obj_name": "multiply_large",
        "call_obj": {
            "entries": ["100", "1000000"],
            "args": (),
            "kwargs": {},
            "log_limit": 0,
            "fixed_time": False,
            "debug": False,
        },
        "full_log": "Enter the first number: 100\nEnter the second number: 1000000\n100 * 1000000 = 1.00e+08\n",
        "log_lines": [
            "Enter the first number: 100\n",
            "Enter the second number: 1000000\n",
            "100 * 1000000 = 1.00e+08\n",
        ],
        "formatted_log": "\n\nline |Input/Output Log:\n"
        + "-" * 70
        + "\n"
        + "   1 |Enter the first number: 100\n"
        + "   2 |Enter the second number: 1000000\n"
        + "   3 |100 * 1000000 = 1.00e+08\n",
        "values": [
            [100],
            [1000000],
            [100, 1000000, 1.00e08],
        ],
    },
]


@pytest.fixture(scope="function", params=complete_user_cases)
def complete_user(request, fix_syspath, tmp_path, monkeypatch):
    """Create a User object for testing."""
    case = request.param
    fake_file = tmp_path / f"{case['module']}.py"
    fake_file.write_text(case["file_text"])
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = User(test, case["module"], case["obj_name"])
    user.call_obj(**case["call_obj"])
    return user, case


def test_read_log_lines(complete_user):
    """Test the User class read_log_lines method."""
    user, case = complete_user
    assert user.read_log_lines() == case["log_lines"]


def test_read_log_line(complete_user):
    """Test the User class read_log_line method."""
    user, case = complete_user
    for i, line in enumerate(case["log_lines"]):
        assert user.read_log_line(line_n=(i + 1)) == line
    with pytest.raises(IndexError) as exc_info:
        user.read_log_line(line_n=(i + 2))
    print(exc_info.value)
    assert "Looking for line 4, but output only has 3 lines" in exc_info.value.args[0]


def test_read_log(complete_user):
    """Test the User class read_log method."""
    user, case = complete_user
    assert user.read_log() == case["full_log"]


def test_format_log(complete_user):
    """Test the User class format_log method."""
    user, case = complete_user
    assert user.format_log() == case["formatted_log"]


def test_empty_format_log(fix_syspath, tmp_path, monkeypatch):
    """Test the User class format_log method with an empty log."""
    fake_file = tmp_path / "empty.py"
    fake_file.write_text("def main():\n    pass\n")
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = User(test, "empty", "main")
    assert user.format_log() == ""


def test_get_values(complete_user):
    """Test the User class get_values method."""
    user, case = complete_user
    for i, values in enumerate(case["values"]):
        assert user.get_values(line_n=(i + 1)) == values
    with pytest.raises(IndexError) as exc_info:
        user.get_values(line_n=(i + 2))
    assert "Looking for line 4, but output only has 3 lines" in exc_info.value.args[0]


def test_get_value(complete_user):
    """Test the User class get_value method."""
    user, case = complete_user
    for i, values in enumerate(case["values"]):
        for j, value in enumerate(values):
            assert user.get_value(line_n=(i + 1), value_n=(j + 1)) == value
    with pytest.raises(IndexError) as exc_info:
        user.get_value(line_n=(i + 1), value_n=(j + 2))
    assert (
        "Looking for the 4th value in the 3rd output line, but only found 3"
        in exc_info.value.args[0]
    )
