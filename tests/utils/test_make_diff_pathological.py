"""Pathological diff inputs built from real EBEC final project output.

`data/code_breakers_lose_game.txt` is the I/O log of the Code Breakers reference
solution for the "lose after 10 wrong guesses" formatting test (6.3k characters,
209 lines).  Twelve consecutive games (76k characters, 2508 lines) approximate a
long session and exceed unittest's own 2**16 character diff threshold.  The
output is dominated by near-identical board rows, which is the worst case for
`difflib.ndiff`: when a student's formatting differs on every line, ndiff pairs
every line with every other line.  Measured with every line differing:

    Python 3.12: 17-40 s    Python 3.13: 30 s    Python 3.14: 0.15 s

Students must still be shown where whitespace differs, and Python's default
`autojunk` heuristic (active at 200+ lines) must not inflate the diff.
"""

import time
import unittest
from pathlib import Path

import pytest

from generic_grader.utils.safe_equal import make_diff, safe_assert_equal

GAMES = 12
TIME_BUDGET = 5.0  # seconds

EXPECTED = (Path(__file__).parent / "data" / "code_breakers_lose_game.txt").read_text()
EXPECTED = EXPECTED * GAMES
EXPECTED_LINES = EXPECTED.splitlines(keepends=True)


def trailing_space(text):
    """Every line ends with a stray space."""
    return "".join(line.rstrip("\n") + " \n" for line in text.splitlines(keepends=True))


def trailing_space_leading_blank(text):
    """Stray trailing spaces and an extra blank line at the top (line counts differ)."""
    return "\n" + trailing_space(text)


def dash_for_o(text):
    """Empty pins drawn as '-' instead of 'o' on every board row."""
    return text.replace(" o ", " - ")


def blank_after_rule(text):
    """An extra blank line after every board rule."""
    return "".join(
        line + ("\n" if line.startswith("   ===") else "")
        for line in text.splitlines(keepends=True)
    )


VARIANTS = {
    "trailing_space": trailing_space,
    "trailing_space_leading_blank": trailing_space_leading_blank,
    "dash_for_o": dash_for_o,
    "blank_after_rule": blank_after_rule,
}


@pytest.mark.parametrize("variant", VARIANTS)
def test_long_output_gets_a_diff_quickly(variant):
    """A diff is produced for long, nearly-every-line-differs output in bounded time."""
    actual = VARIANTS[variant](EXPECTED)

    start = time.perf_counter()
    diff = make_diff(actual, EXPECTED)
    elapsed = time.perf_counter() - start

    assert diff, "expected a diff for long output, got an empty string"
    assert elapsed < TIME_BUDGET, f"make_diff took {elapsed:.1f}s"


@pytest.mark.parametrize("variant", ["trailing_space", "trailing_space_leading_blank"])
def test_whitespace_only_differences_are_marked(variant):
    """Every non-blank line that differs only by whitespace gets a '?' marker."""
    actual = VARIANTS[variant](EXPECTED)

    diff = make_diff(actual, EXPECTED)

    markers = [line for line in diff.splitlines() if line.startswith("?")]
    non_blank = [line for line in EXPECTED_LINES if line.strip()]
    assert len(markers) >= len(non_blank)


def test_diff_is_minimal_when_only_blank_lines_are_inserted():
    """Repeated lines must not make the diff report more than the inserted lines."""
    actual = blank_after_rule(EXPECTED)
    inserted = actual.count("\n") - EXPECTED.count("\n")

    diff = make_diff(actual, EXPECTED)

    changed = [line for line in diff.splitlines() if line[:2] in ("- ", "+ ")]
    assert len(changed) == inserted


class _DummyTestCase(unittest.TestCase):
    """Minimal TestCase used to call safe_assert_equal."""


@pytest.mark.parametrize("variant", ["trailing_space", "dash_for_o"])
def test_exact_match_failure_shows_diff_for_long_output(variant):
    """The default (exact match) path shows a diff, not a truncated repr."""
    actual = VARIANTS[variant](EXPECTED)

    start = time.perf_counter()
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(_DummyTestCase(), actual, EXPECTED, msg="\n\nHint: ...")
    elapsed = time.perf_counter() - start

    message = str(exc_info.value)
    assert "\n? " in message
    assert "Hint: ..." in message
    assert elapsed < TIME_BUDGET, f"safe_assert_equal took {elapsed:.1f}s"
