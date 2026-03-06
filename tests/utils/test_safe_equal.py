"""Tests for the safe_equal utility."""

import unittest

import pytest

from generic_grader.utils.safe_equal import _MAX_PFORMAT_CHARS, safe_assert_equal


class _DummyTestCase(unittest.TestCase):
    """Minimal TestCase used to call safe_assert_equal."""

    pass


@pytest.fixture()
def tc():
    """Provide a fresh TestCase instance."""
    return _DummyTestCase()


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
    assert (
        "^" in message
    ), "Expected assertEqual-style diff with '^' markers for small values"


def test_safe_assert_equal_large_diff_is_truncated(tc):
    """Large differing values should produce a truncated repr, not a full diff."""
    large_a = {f"key_{i}": f"value_a_{i}" for i in range(500)}
    large_b = {f"key_{i}": f"value_b_{i}" for i in range(500)}
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, large_a, large_b, msg="")
    message = str(exc_info.value)
    # The truncated repr should contain '...' from reprlib truncation.
    assert "..." in message, "Expected truncated repr with '...' for large values"
    # The message should NOT contain the full 500 keys.
    assert (
        "key_499" not in message
    ), "Expected repr to be truncated, but found the last key"


def test_safe_assert_equal_large_values_complete_quickly(tc):
    """Large differing values must not hang — regression test for the O(n²) bug."""
    large_a = {f"key_{i}": f"value_a_{i}" for i in range(500)}
    large_b = {f"key_{i}": f"value_b_{i}" for i in range(500)}

    import time

    start = time.time()
    with pytest.raises(AssertionError):
        safe_assert_equal(tc, large_a, large_b, msg="")
    elapsed = time.time() - start

    assert (
        elapsed < 10
    ), f"safe_assert_equal on large diffs took {elapsed:.1f}s; expected < 10s"


def test_safe_assert_equal_threshold_boundary(tc):
    """Values just above the threshold should take the truncated path."""
    import pprint

    # Build up a dict one key at a time until its pformat crosses the
    # threshold.  This avoids rebuilding from scratch each iteration.
    d = {}
    n = 0
    while len(pprint.pformat(d)) * 2 <= _MAX_PFORMAT_CHARS:
        d[f"k{n}"] = f"v{n}"
        n += 1

    other = {k: f"x{k[1:]}" for k in d}
    with pytest.raises(AssertionError) as exc_info:
        safe_assert_equal(tc, d, other, msg="")
    message = str(exc_info.value)
    # Should be the truncated path — no '^' markers, but has '...'.
    assert "..." in message


def test_safe_assert_equal_includes_msg(tc):
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
