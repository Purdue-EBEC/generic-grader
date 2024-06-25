import pytest

from generic_grader.utils.docs import (
    calc_log_limit,
    make_call_str,
    make_line_range,
    ordinalize,
    oxford_list,
)

str_cases = [
    {"func_name": "main", "args": [], "kwargs": {}, "expected": "main()"},
    {"func_name": "main", "args": [1, 2, 3], "kwargs": {}, "expected": "main(1, 2, 3)"},
    {
        "func_name": "main",
        "args": [1, 2, 3],
        "kwargs": {"x": 4, "y": 5},
        "expected": "main(1, 2, 3, x=4, y=5)",
    },
]


@pytest.mark.parametrize("case", str_cases)
def test_make_call_str(case):
    """Test make_call_str to ensure it formats function calls correctly."""
    assert (
        make_call_str(case["func_name"], case["args"], case["kwargs"])
        == case["expected"]
    )


ord_cases = [
    {"n": 1, "expected": "1st"},
    {"n": 2, "expected": "2nd"},
    {"n": 3, "expected": "3rd"},
    {"n": 4, "expected": "4th"},
    {"n": 11, "expected": "11th"},
    {"n": 12, "expected": "12th"},
    {"n": 13, "expected": "13th"},
    {"n": 21, "expected": "21st"},
    {"n": 22, "expected": "22nd"},
    {"n": 23, "expected": "23rd"},
    {"n": 24, "expected": "24th"},
    {"n": 111, "expected": "111th"},
    {"n": 112, "expected": "112th"},
    {"n": 113, "expected": "113th"},
    {"n": 121, "expected": "121st"},
    {"n": 122, "expected": "122nd"},
    {"n": 123, "expected": "123rd"},
    {"n": 124, "expected": "124th"},
]


@pytest.mark.parametrize("case", ord_cases)
def test_ordinalize(case):
    """Test ordinalize to ensure it formats numbers correctly."""
    assert ordinalize(case["n"]) == case["expected"]


calc_log_cases = [
    {"expected_log": "log message", "expected": 216},
    {"expected_log": "log message" * 10, "expected": 365},
    {"expected_log": "log message" * 100, "expected": 1850},
]


@pytest.mark.parametrize("case", calc_log_cases)
def test_calc_log_limit(case):
    """Test calc_log_limit to ensure it calculates log limits correctly."""
    assert calc_log_limit(case["expected_log"]) == case["expected"]


line_range_cases = [
    {"start": 1, "n_lines": 1, "expected": "line 1"},
    {"start": 1, "n_lines": 3, "expected": "lines 1 through 3"},
    {"start": 1, "n_lines": 0, "expected": "lines 1 through the end"},
    {"start": 3, "n_lines": 1, "expected": "line 3"},
    {"start": 3, "n_lines": 0, "expected": "lines 3 through the end"},
    {"start": 3, "n_lines": 3, "expected": "lines 3 through 5"},
]


@pytest.mark.parametrize("case", line_range_cases)
def test_make_line_range(case):
    """Test make_line_range to ensure it formats line ranges correctly."""
    assert make_line_range(case["start"], case["n_lines"]) == case["expected"]


oxford_cases = [
    {"sequence": [], "expected": ""},
    {"sequence": ["one"], "expected": "one"},
    {"sequence": ["one", "two"], "expected": "one and two"},
    {"sequence": ["one", "two", "three"], "expected": "one, two, and three"},
    {
        "sequence": ["one", "two", "three", "four"],
        "expected": "one, two, three, and four",
    },
]


@pytest.mark.parametrize("case", oxford_cases)
def test_oxford_list(case):
    """Test oxford_list to ensure it formats lists correctly."""
    assert oxford_list(case["sequence"]) == case["expected"]
