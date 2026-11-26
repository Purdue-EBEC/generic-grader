"""Tests for the safe_equal utility."""

import unittest

import pytest

from generic_grader.utils import safe_equal as safe_equal_module
from generic_grader.utils.safe_equal import (
    make_diff,
    safe_assert_equal,
)


class _DummyTestCase(unittest.TestCase):
    """Minimal TestCase used to call safe_assert_equal."""


@pytest.fixture()
def tc():
    """Provide a fresh TestCase instance."""
    return _DummyTestCase()


@pytest.fixture()
def small_cap(monkeypatch):
    """Lower the size cap so the truncation path is cheap to reach."""
    monkeypatch.setattr(safe_equal_module, "_MAX_PFORMAT_CHARS", 2000)
    return 2000


def test_safe_assert_equal_pass(tc):
    """Equal values should not raise."""
    safe_assert_equal(tc, {"a": 1, "b": 2}, {"a": 1, "b": 2}, msg="hint")


def test_safe_assert_equal_small_diff_uses_assertEqual(tc):
    """Small differing values should produce the standard diff with '^' markers."""
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, {"a": 1, "b": 2}, {"a": 1, "b": 3}, msg="")
    message = str(exc_info.value)
    # assertEqual's assertDictEqual produces ndiff output with +/- lines
    # and '^' character-level markers.
    assert "^" in message, (
        "Expected assertEqual-style diff with '^' markers for small values"
    )


def test_safe_assert_equal_large_diff_is_truncated(tc, small_cap):
    """Large differing values should produce a truncated repr, not a full diff."""
    large_a = {f"key_{i}": f"value_a_{i}" for i in range(500)}
    large_b = {f"key_{i}": f"value_b_{i}" for i in range(500)}
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, large_a, large_b, msg="")
    message = str(exc_info.value)
    # The truncated repr should contain '...' from reprlib truncation.
    assert "..." in message, "Expected truncated repr with '...' for large values"
    # The message should NOT contain the full 500 keys.
    assert "key_499" not in message, (
        "Expected repr to be truncated, but found the last key"
    )


def test_safe_assert_equal_large_values_complete_quickly(tc, small_cap):
    """Large differing values must not hang — regression test for the O(n²) bug."""
    large_a = {f"key_{i}": f"value_a_{i}" for i in range(500)}
    large_b = {f"key_{i}": f"value_b_{i}" for i in range(500)}

    import time

    start = time.time()
    with pytest.raises(AssertionError):
        safe_assert_equal(tc, large_a, large_b, msg="")
    elapsed = time.time() - start

    assert elapsed < 10, (
        f"safe_assert_equal on large diffs took {elapsed:.1f}s; expected < 10s"
    )


def test_safe_assert_equal_threshold_boundary(tc, small_cap):
    """Values just above the threshold should take the truncated path."""
    import pprint

    # Build up a dict one key at a time until its pformat crosses the
    # threshold.  This avoids rebuilding from scratch each iteration.
    d = {}
    n = 0
    while len(pprint.pformat(d)) * 2 <= small_cap:
        d[f"k{n}"] = f"v{n}"
        n += 1

    other = {k: f"x{k[1:]}" for k in d}
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, d, other, msg="")
    message = str(exc_info.value)
    # Should be the truncated path — no '^' markers, but has '...'.
    assert "..." in message


def test_safe_assert_equal_includes_msg(tc, small_cap):
    """The custom msg should appear in the error for both paths."""
    # Small path
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, 1, 2, msg="custom hint")
    assert "custom hint" in str(exc_info.value)

    # Large path
    large_a = {f"key_{i}": f"a_{i}" for i in range(500)}
    large_b = {f"key_{i}": f"b_{i}" for i in range(500)}
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, large_a, large_b, msg="custom hint")
    assert "custom hint" in str(exc_info.value)


make_diff_cases = [
    {
        "actual": "Hello World!",
        "expected": "Hello World!",
        "expected_diff": "  Hello World!\n",
    },
    {
        "actual": "Hello World!",
        "expected": "Hello World",
        "expected_diff": "- Hello World!\n?            -\n+ Hello World\n",
    },
    {
        "actual": "Hello World",
        "expected": "Hello World!",
        "expected_diff": "- Hello World\n+ Hello World!\n?            +\n",
    },
]


@pytest.mark.parametrize("case", make_diff_cases)
def test_make_diff(case):
    """Test that the make_diff function works as expected."""
    diff = make_diff(case["actual"], case["expected"])
    assert diff == case["expected_diff"]


def test_make_diff_returns_empty_for_large_input(small_cap):
    """make_diff returns an empty string when inputs exceed the size threshold."""
    large_a = "a\n" * 1500
    large_b = "b\n" * 1500
    assert make_diff(large_a, large_b) == ""


def test_safe_assert_equal_gates_strings_on_raw_length(tc, small_cap):
    """Strings are sized by raw length, as make_diff does, not by pformat."""
    # 1800 raw characters in total, but pformat adds quotes and escapes per line.
    actual = "ab\n" * 300
    expected = "ac\n" * 300
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, actual, expected, msg="")
    message = str(exc_info.value)
    assert "- ab\n" in message
    assert "+ ac\n" in message


@pytest.fixture()
def small_diff_cap(monkeypatch):
    """Lower the cap on diff size so truncation is cheap to reach."""
    monkeypatch.setattr(safe_equal_module, "_MAX_DIFF_CHARS", 500)
    return 500


def test_make_diff_truncates_long_diff(small_diff_cap):
    """An oversized diff is cut at a line boundary with a note."""
    diff = make_diff("a\n" * 1000, "b\n" * 1000)
    assert len(diff) < small_diff_cap + 200
    assert "diff truncated" in diff
    assert diff.startswith("- a\n")


def test_make_diff_does_not_truncate_short_diff(small_diff_cap):
    """A diff within the cap is returned unchanged."""
    assert make_diff("Hello World", "Hello World!\n") == (
        "- Hello World\n+ Hello World!\n?            +\n"
    )


def test_safe_assert_equal_truncates_long_diff_but_keeps_msg(tc, small_diff_cap):
    """The student-facing hint stays visible when the diff is truncated."""
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, "a\n" * 1000, "b\n" * 1000, msg="\n\nHint: check it")
    message = str(exc_info.value)
    assert "diff truncated" in message
    assert len(message) < small_diff_cap + 300
    assert message.endswith("Hint: check it")
