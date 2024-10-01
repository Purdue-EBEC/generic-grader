import pytest

from generic_grader.utils.math_utils import calc_log_limit, n_trials

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


calc_log_cases = [
    {"expected_log": "", "expected": 200},
    {"expected_log": "log message", "expected": 216},
    {"expected_log": "log message" * 10, "expected": 365},
    {"expected_log": "log message" * 100, "expected": 1850},
]


@pytest.mark.parametrize("case", calc_log_cases)
def test_calc_log_limit(case):
    """Test calc_log_limit to ensure it calculates log limits correctly."""
    assert calc_log_limit(case["expected_log"]) == case["expected"]
