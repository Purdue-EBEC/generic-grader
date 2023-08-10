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

    @weighted
    def func(*args, **kwargs):
        """Some test function."""
        pass

    return case, func


def test_weighted_decorator(case_test_weighted_method):
    """Test that the weighted decorator sets the weight attribute."""
    case, func = case_test_weighted_method

    # The __weight__ attribute is set when the decorated function is called.
    func(*case["args"], **case["kwargs"])

    assert hasattr(func, "__weight__")
    assert func.__weight__ == case["weight"]


# TODO: Check results.json after running gradescope test runner.
