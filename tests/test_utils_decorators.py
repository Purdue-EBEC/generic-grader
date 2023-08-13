import unittest

import pytest

from generic_grader.utils.decorators import weighted
from generic_grader.utils.options import Options

# Check weight attribute of method with:
#   - no options argument
#   - options as the first positional argument
#   - options as a middle positional argument
#   - options as a keyword argument
cases = [
    {
        "weight": 0,  # The default weight
        "args": (),
        "kwargs": {},
    },
    {
        "weight": 1,
        "args": (Options(weight=1),),
        "kwargs": {},
    },
    {
        "weight": 2,
        "args": ("spam", False, Options(weight=2), 42),
        "kwargs": {},
    },
    {
        "weight": 3,
        "args": (),
        "kwargs": {"spam": False, "options": Options(weight=3), "eggs": 3},
    },
]


@pytest.fixture(params=cases)
def case_test_weighted_method(request):
    """Arrange parameterized test cases."""
    case = request.param

    class TestClass(unittest.TestCase):
        """A dummy test class."""

        @weighted
        def test_func(*args, **kwargs):
            """Some test function."""
            pass

    return case, TestClass().test_func


def test_weighted_decorator(case_test_weighted_method):
    """Test that the weighted decorator sets the weight attribute."""
    case, func = case_test_weighted_method

    # The __weight__ attribute is set when the decorated function is called.
    func(*case["args"], **case["kwargs"])

    assert hasattr(func, "__weight__")
    assert func.__weight__ == case["weight"]


# Check that class methods decorated with weighted:
#   - do not have a __score__ attribute before calling set_score
#   - have a __score__ attribute set to score after calling set_score
def test_weighted_decorator_set_score():
    """Test that the weighted decorator sets the score attribute."""

    class TestClass(unittest.TestCase):
        """A dummy test class."""

        @weighted
        def test_func(self, options):
            """Some test function."""
            self.set_score(0.5)

    test = TestClass()
    assert not hasattr(test.test_func, "__score__")
    test.test_func(options=Options(weight=1))
    assert test.test_func.__score__ == 0.5


# TODO: Check results.json after running gradescope test runner.
