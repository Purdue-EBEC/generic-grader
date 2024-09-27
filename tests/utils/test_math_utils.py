import pytest

from generic_grader.utils.math_utils import n_trials

cases = [
    # Input, Expected
    (1, 9, 30),
    (2, 9, 52),
    (3, 9, 73),
    (4, 9, 93),
    (5, 9, 114),
    (1, 6, 20),
    (2, 6, 35),
    (3, 6, 49),
    (4, 6, 62),
    (5, 6, 76),
]


@pytest.mark.parametrize("num_cases, tolerance, expected", cases)
def test_n_trials(num_cases, tolerance, expected):
    """Test that the n_trials function returns the expected value."""
    assert n_trials(num_cases, tolerance) == expected
