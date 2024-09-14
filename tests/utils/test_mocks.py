import pytest

from generic_grader.utils.exceptions import ExcessFunctionCallError
from generic_grader.utils.mocks import (
    make_mock_function,
    make_mock_function_noop,
    make_mock_function_raise_error,
)


def test_make_mock_function_raise_error():
    """Make sure the mock function always raises the correct error every time it is run."""
    func_name = "test_func"
    error = ValueError

    mock_name, mocked_func = make_mock_function_raise_error(func_name, error)

    with pytest.raises(ValueError) as exc_info:
        mocked_func("spam", spam="spam spam")

    assert func_name == mock_name
    assert (
        str(exc_info.value)
        == "Your program unexpectedly called `test_func('spam', spam='spam spam')`."
    )


def test_make_mock_function_noop():
    """Make sure the noop mock function always does nothing"""
    func_name = "test_func"

    mock_name, mocked_func = make_mock_function_noop(func_name)

    mocked_func()
    mocked_func("str", 1, spam="spam")
    assert func_name == mock_name


def test_make_mock_function():
    """Make sure the regular mock function returns the correct values and then raises the correct error."""

    func_name = "test_func"
    return_values = (1, 2, 3, 4, 5)
    mock_name, mocked_func = make_mock_function(func_name, return_values)

    for val in return_values:
        assert val == mocked_func("str", 1, spam="spam")

    with pytest.raises(ExcessFunctionCallError) as exc_info:
        mocked_func()

    assert (
        str(exc_info.value)
        == "  Your program called the `test_func` function more times than\n  expected.\n\nHint:\n  Make sure your program isn't stuck in an infinite loop."
    )
