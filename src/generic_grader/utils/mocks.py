from copy import deepcopy

from generic_grader.utils.docs import make_call_str
from generic_grader.utils.exceptions import ExcessFunctionCallError


def make_mock_function_noop(func_name):
    """Create a mock version of func_name that does nothing."""

    def mock(*args, **kwargs):
        pass

    return func_name, mock


def make_mock_function(func_name, iterable):
    """
    Create a mock version of func_name that returns values from iterable.

    The mocked version returns the next value in iterable each time it gets called, and
    raises our ExcessFunctionCallError if it gets called more times than expected.
    """

    # Use separate copies of the iterable in each mocked function to prevent
    # changes to mutable elements in one from affecting the other.
    i = iter(deepcopy(iterable))

    def mock(*args, **kwargs):
        try:
            return next(i)
        except StopIteration as e:
            raise ExcessFunctionCallError(func_name) from e

    return func_name, mock


def make_mock_function_raise_error(func_name, error):
    """
    Create a mock version of func_name that raises error each time it's called.
    """

    def mock(*args, **kwargs):
        call_str = make_call_str(func_name, args, kwargs)
        error_msg = f"Your program unexpectedly called `{call_str}`."
        raise error(error_msg)

    return func_name, mock
