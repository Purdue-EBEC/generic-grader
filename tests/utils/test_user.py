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
    UserInitializationError,
    UserTimeoutError,
)
from generic_grader.utils.options import Options
from generic_grader.utils.user import (
    RefUser,
    SubUser,
    __User__,
    memory_limit,
    time_limit,
)

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
    log = __User__.LogIO(case["limit"])
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
        "options": Options(sub_module="hello_user_1"),
        "file_text": "def main():\n    print('Hello, User!')",
        "result": "Hello, User!\n",
    },
    {
        "options": Options(sub_module="input_user_1", entries=(["Jack"])),
        "module": "input_user_1",
        "file_text": "def main():\n    name = input('What is your name? ')\n    print(f'Hello, {name}!')",
        "result": "What is your name? Jack\nHello, Jack!\n",
    },
    {
        "options": Options(
            sub_module="print_user_arg_1", args=(["Jack"]), obj_name="user_func"
        ),
        "file_text": "def user_func(user):\n    print(f'Hello, {user}!')",
        "result": "Hello, Jack!\n",
    },
    {
        "options": Options(
            sub_module="print_user_kwargs_1",
            kwargs={"user": "Jack", "greeting": "Hi"},
            obj_name="user_func",
        ),
        "file_text": "def user_func(user, greeting):\n    print(f'{greeting}, {user}!')\n",
        "result": "Hi, Jack!\n",
    },
    {
        "options": Options(sub_module="hello_user_2", log_limit=13),
        "file_text": "def main():\n    print('Hello, User!')",
        "result": "Hello, User!\n",
    },
    {
        "options": Options(
            sub_module="freeze_time_1", fixed_time=datetime(2021, 1, 1, 0, 0, 0)
        ),
        "file_text": "import datetime\n\ndef main():\n    print(datetime.datetime.now())",
        "result": "2021-01-01 00:00:00\n",
    },
    {
        "options": Options(
            sub_module="int_patch_1",
            entries=(["100"]),
            patches=[{"args": ["builtins.int", lambda x: x * 2]}],
        ),
        "file_text": "def main():\n    x = input('Enter a string: ')\n    print(f'{x} * 2 = {int(x)}')",
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
    options = case["options"]
    fake_file = tmp_path / f"{options.sub_module}.py"
    fake_file.write_text(case["file_text"])
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Create a User object
    user = SubUser(test, options)
    # Call the object
    user.call_obj(options)
    # Check
    assert user.log.getvalue() == case["result"]


call_obj_fail = [
    {  # Too many entries
        "options": Options(sub_module="hello_user_3", entries=(["Jack"])),
        "file_text": "def main():\n    print('Hello, User!')",
        "result": "Hello, User!\n",
        "error": AssertionError,
    },
    {  # Missing entry
        "options": Options(sub_module="input_user_2"),
        "file_text": "def main():\n    name = input('What is your name? ')\n    print(f'Hello, {name}!')",
        "result": "What is your name? ",
        "error": EndOfInputError,
    },
    {  # Missing argument
        "options": Options(sub_module="print_user_arg_2", obj_name="user_func"),
        "file_text": "def user_func(user):\n    print(f'Hello, {user}!')\n",
        "result": "",
        "error": TypeError,
    },
    {  # Missing keyword argument
        "options": Options(
            sub_module="print_user_kwargs_2",
            kwargs={"greeting": "Hi"},
            obj_name="user_func",
        ),
        "file_text": "def user_func(user, greeting):\n    print(f'{greeting}, {user}!')\n",
        "result": "",
        "error": TypeError,
    },
    {  # Log limit exceeded
        "options": Options(sub_module="hello_user_4", log_limit=5),
        "file_text": "def main():\n    print('Hello, User!')",
        "result": "Hello, User!",  # No newline
        "error": LogLimitExceededError,
    },
    {  # Exit function
        "options": Options(sub_module="hello_user_5"),
        "module": "hello_user_5",
        "file_text": "def main():\n     print('Hello, User!')\n     exit()",
        "result": "Hello, User!\n",
        "error": ExitError,
    },
    {  # Quit function
        "options": Options(sub_module="hello_user_6"),
        "file_text": "def main():\n    print('Hello, User!')\n    quit()",
        "result": "Hello, User!\n",
        "error": QuitError,
    },
]


@pytest.mark.parametrize("case", call_obj_fail)
def test_failing_call_obj(case, fix_syspath, tmp_path, monkeypatch):
    """Test the User class call_obj method."""
    # Set up the test environment
    options = case["options"]
    fake_file = tmp_path / f"{options.sub_module}.py"
    fake_file.write_text(case["file_text"])
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Create a User object
    user = SubUser(test, options)
    # Call the object
    with pytest.raises(case["error"]):
        user.call_obj(options)
    assert user.log.getvalue() == case["result"]


def test_failing_call_obj_error(fix_syspath, tmp_path, monkeypatch):
    """Make sure `error_msg` is properly shown when an error occurs."""
    options = Options(sub_module="error_user_1", entries=(["Jack", "AJ"]))
    fake_file = tmp_path / f"{options.sub_module}.py"
    fake_file.write_text(
        "def main():\n    name = input('What is your name? ')\n    print(f'Hello, {name}!')"
    )
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = SubUser(test, options)
    with pytest.raises(EndOfInputError) as exc_info:
        user.call_obj(options)
    assert (
        f"Your `{options.obj_name}` malfunctioned when called as `main()` with entries\n  {options.entries}."
        in exc_info.value.args[0]
    )


def test_debug_call_obj(capsys, fix_syspath, tmp_path, monkeypatch):
    """Test the debug option in the User class call_obj method."""
    # Set up the test environment
    options = Options(sub_module="hello_user_7", debug=True)
    fake_file = tmp_path / f"{options.sub_module}.py"
    fake_file.write_text("def main():\n    print('Hello, User!')")
    monkeypatch.chdir(tmp_path)
    # Create a fake test object
    test = FakeTest()
    # Create a User object
    user = SubUser(test, options)
    # Call the object
    user.call_obj(options)
    # Check
    captured = capsys.readouterr()
    assert captured.out == "Hello, User!\n\n"
    assert user.log.getvalue() == "Hello, User!\n"
    assert captured.err == ""


complete_user_cases = [
    {
        "options": Options(
            sub_module="add_user_1", entries=(["1", "10"]), obj_name="add_number"
        ),
        "file_text": "def add_number():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n",
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
        "options": Options(
            sub_module="add_decimals_1",
            entries=(["1.1", "10.1"]),
            obj_name="add_decimal",
        ),
        "file_text": "def add_decimal():\n    num1 = float(input('Enter the first number: '))\n    num2 = float(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n",
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
        "options": Options(
            sub_module="add_negative_1",
            entries=(["-1", "-10"]),
            obj_name="add_negative",
        ),
        "file_text": "def add_negative():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} + {num2} = {num1 + num2}')\n",
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
        "options": Options(
            sub_module="multiply_large_1",
            entries=(["100", "1000000"]),
            obj_name="multiply_large",
        ),
        "file_text": "def multiply_large():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} * {num2} = {(num1 * num2):,}')",
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
        "options": Options(
            sub_module="multiply_large_2",
            entries=(["100", "1000000"]),
            obj_name="multiply_large",
        ),
        "file_text": "def multiply_large():\n    num1 = int(input('Enter the first number: '))\n    num2 = int(input('Enter the second number: '))\n    print(f'{num1} * {num2} = {(num1 * num2):.2e}')",
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
    options = case["options"]
    fake_file = tmp_path / f"{options.sub_module}.py"
    fake_file.write_text(case["file_text"])
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = SubUser(test, options)
    user.call_obj(options)
    return user, case


def test_read_log_lines(complete_user):
    """Test the User class read_log_lines method."""
    user, case = complete_user
    assert user.read_log_lines(Options()) == case["log_lines"]


def test_read_log_line(complete_user):
    """Test the User class read_log_line method."""
    user, case = complete_user
    for i, line in enumerate(case["log_lines"]):
        assert user.read_log_line(Options(line_n=(i + 1))) == line
    with pytest.raises(IndexError) as exc_info:
        user.read_log_line(Options(line_n=(i + 2)))
    print(exc_info.value)
    assert "Looking for line 4, but output only has 3 lines" in exc_info.value.args[0]


def test_read_log(complete_user):
    """Test the User class read_log method."""
    user, case = complete_user
    assert user.read_log(Options()) == case["full_log"]


def test_format_log(complete_user):
    """Test the User class format_log method."""
    user, case = complete_user
    assert user.format_log(Options()) == case["formatted_log"]


def test_empty_format_log(fix_syspath, tmp_path, monkeypatch):
    """Test the User class format_log method with an empty log."""
    fake_file = tmp_path / "empty.py"
    fake_file.write_text("def main():\n    pass\n")
    monkeypatch.chdir(tmp_path)
    test = FakeTest()
    user = SubUser(test, Options(sub_module="empty"))
    assert user.format_log(Options()) == ""


def test_get_values(complete_user):
    """Test the User class get_values method."""
    user, case = complete_user
    for i, values in enumerate(case["values"]):
        assert user.get_values(Options(line_n=(i + 1))) == values
    with pytest.raises(IndexError) as exc_info:
        user.get_values(Options(line_n=(i + 2)))
    assert "Looking for line 4, but output only has 3 lines" in exc_info.value.args[0]


def test_get_value(complete_user):
    """Test the User class get_value method."""
    user, case = complete_user
    for i, values in enumerate(case["values"]):
        for j, value in enumerate(values):
            assert user.get_value(Options(line_n=(i + 1), value_n=(j + 1))) == value
    with pytest.raises(IndexError) as exc_info:
        user.get_value(Options(line_n=(i + 1), value_n=(j + 2)))
    assert (
        "Looking for the 4th value in the 3rd output line, but only found 3"
        in exc_info.value.args[0]
    )


def test_RefSubUser(fix_syspath, tmp_path, monkeypatch):
    """Make sure the RefUser class is instantiated properly."""
    options = Options(ref_module="reference")
    test = FakeTest()
    fake_file = tmp_path / "reference.py"
    fake_file.write_text("def main():\n    pass\n")
    monkeypatch.chdir(tmp_path)
    user = RefUser(test, options)
    assert user.module == "reference"
    assert isinstance(user, RefUser)
    assert issubclass(RefUser, __User__)


def test_SubUser(fix_syspath, tmp_path, monkeypatch):
    """Make sure the SubUser class is instantiated properly."""
    options = Options(sub_module="submission")
    test = FakeTest()
    fake_file = tmp_path / "submission.py"
    fake_file.write_text("def main():\n    pass\n")
    monkeypatch.chdir(tmp_path)
    user = SubUser(test, options)
    assert user.module == "submission"
    assert isinstance(user, SubUser)
    assert issubclass(SubUser, __User__)


def test_disallow_User():
    """Test that the User class is not directly instantiated."""
    with pytest.raises(UserInitializationError):
        __User__(FakeTest(), Options())
