import pytest

from generic_grader.utils.exceptions import (
    EndOfInputError,
    ExcessFunctionCallError,
    ExitError,
    LogLimitExceededError,
    QuitError,
    TurtleDoneError,
    TurtleWriteError,
    UserInitializationError,
    UserTimeoutError,
    format_error_msg,
    indent,
    wrapper,
)

# TODO Add a test for the handle_error function. This was left out because the function needs to be changed after partiy is achieved.


def test_wrapper():
    """Test the wrapper that is used to format error messages."""
    assert wrapper.initial_indent == 2 * " "
    assert wrapper.subsequent_indent == 2 * " "


indent_cases = [
    {"input": "Hello World!", "output": "  Hello World!", "padding": 2},
    {"input": "Hello World!", "output": "    Hello World!", "padding": 4},
    # {"input": "Hello World!\n\nGoodbye World!", "output": "  Hello World!\n\n  Goodbye World!", "padding": 2},
    # {"input": "Hello World!\n", "output": "Hello World!\n", "padding": 0},
]


@pytest.mark.parametrize("case", indent_cases)
def test_indent(case):
    """Test the indent function."""
    assert case["output"] == indent(case["input"], pad=(case["padding"] * " "))


format_error_msg_cases = [
    {
        "error_msg": "This is an error message.",
        "hint": "This is a hint.",
        "output": "  This is an error message.\n\nHint:\n  This is a hint.",
    },
    {
        "error_msg": "This is an error message.",
        "hint": None,
        "output": "  This is an error message.",
    },
]


@pytest.mark.parametrize("case", format_error_msg_cases)
def test_format_error_msg(case):
    """Test the format_error_msg function."""
    assert case["output"] == format_error_msg(case["error_msg"], case["hint"])


custom_errors = [
    {
        "error": ExitError(),
        "expected": "  Calling the `exit()` function is not allowed in this course.\n\nHint:\n  Try using a `return` statement instead.",
    },
    {
        "error": ExitError("this is a hint"),
        "expected": "  Calling the `exit()` function is not allowed in this course.\n\nHint:\n  this is a hint  Try using a `return` statement instead.",
    },
    {
        "error": QuitError(),
        "expected": "  Calling the `quit()` function is not allowed in this course.\n\nHint:\n  Try using a `return` statement instead.",
    },
    {
        "error": QuitError("this is a hint"),
        "expected": "  Calling the `quit()` function is not allowed in this course.\n\nHint:\n  this is a hint  Try using a `return` statement instead.",
    },
    {
        "error": LogLimitExceededError(),
        "expected": "  Your program produced much more output than was expected.\n\nHint:\n  Make sure your program isn't stuck in an infinite loop.",
    },
    {
        "error": LogLimitExceededError("this is a hint"),
        "expected": "  Your program produced much more output than was expected.\n\nHint:\n  this is a hint  Make sure your program isn't stuck in an infinite\n  loop.",
    },
    {
        "error": UserTimeoutError(),
        "expected": "  Your program ran for longer than expected.\n\nHint:\n  Make sure your program isn't stuck in an infinite loop.",
    },
    {
        "error": UserTimeoutError("this is a hint"),
        "expected": "  Your program ran for longer than expected.\n\nHint:\n  this is a hint  Make sure your program isn't stuck in an infinite\n  loop.",
    },
    {
        "error": EndOfInputError(),
        "expected": "  Your program requested user input more times than expected.\n\nHint:\n  Make sure your program isn't stuck in an infinite loop.",
    },
    {
        "error": EndOfInputError("this is a hint"),
        "expected": "  Your program requested user input more times than expected.\n\nHint:\n  this is a hint  Make sure your program isn't stuck in an infinite\n  loop.",
    },
    {
        "error": TurtleWriteError(),
        "expected": "\n\nHint:\n  The turtle module's `write` function is not allowed in this\n  exercise.  Try using turtle movement commands to draw each letter\n  instead.",
    },
    {
        "error": TurtleDoneError(),
        "expected": "\n\nHint:\n  The turtle module's `done` function should not be called from within\n  any of your functions.  The only call to `done()` in your program\n  should be the one included in the exercise template.",
    },
    {
        "error": ExcessFunctionCallError("function_name"),
        "expected": "  Your program called the `function_name` function more times than\n  expected.\n\nHint:\n  Make sure your program isn't stuck in an infinite loop.",
    },
    {
        "error": ExcessFunctionCallError("function_name", "this is a hint"),
        "expected": "  Your program called the `function_name` function more times than\n  expected.\n\nHint:\n  this is a hint  Make sure your program isn't stuck in an infinite\n  loop.",
    },
    {
        "error": UserInitializationError(),
        "expected": "  The User class should not be directly instantiated. Use `RefUser` or\n  SubUser` instead.",
    },
]


@pytest.mark.parametrize("case", custom_errors)
def test_errors_classes(case):
    """Test the custom error classes."""
    assert str(case["error"]) == case["expected"]
