import unittest

import pytest
from parameterized import param, parameterized

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
def case_weighted_test_class(request):
    """Arrange parameterized test cases."""

    case = request.param
    the_params = [
        param(*case["args"], **case["kwargs"]),
    ]

    class TestClass(unittest.TestCase):
        """A dummy test class."""

        @parameterized.expand(the_params)
        @weighted
        def test_func(self, *args, **kwargs):
            """Some test function."""
            pass

    return case, TestClass


def test_weighted_decorator(case_weighted_test_class):
    """Test that the weighted decorator sets the weight attribute.

    The weighted decorator needs the test case to be "run" instead of called
    directly, to ensure the class cleanup method it adds gets called."""

    case, TestClass = case_weighted_test_class

    # The __weight__ attribute is set when the test runs.
    test_suite = unittest.TestLoader().loadTestsFromTestCase(TestClass)
    test_suite.run(unittest.TestResult())

    test_case_names = unittest.TestLoader().getTestCaseNames(TestClass)
    for test_case_name in test_case_names:
        test_case = getattr(TestClass, test_case_name)
        assert hasattr(test_case, "__weight__")
        assert test_case.__weight__ == case["weight"]


# Check that class methods decorated with weighted:
#   - do not have a __score__ attribute before calling set_score
#   - have a __score__ attribute set to score after calling set_score
def test_weighted_decorator_set_score():
    """Test that the weighted decorator sets the score attribute."""
    the_params = [
        param(Options(weight=1)),
        param(Options(weight=2)),
    ]

    class TestClass(unittest.TestCase):
        """A dummy test class."""

        @parameterized.expand(the_params)
        @weighted
        def test_func(self, options):
            """Some test function."""
            score = options.weight / 2
            self.set_score(self, score)

    test = TestClass()
    # The __score__ attribute is not set until set_score is called.
    assert not hasattr(test.test_func_0, "__score__")
    assert not hasattr(test.test_func_1, "__score__")

    test_suite = unittest.TestLoader().loadTestsFromTestCase(TestClass)
    test_suite.run(unittest.TestResult())

    assert test.test_func_0.__score__ == 0.5
    assert test.test_func_1.__score__ == 1


# TODO: Check results.json after running gradescope test runner.
