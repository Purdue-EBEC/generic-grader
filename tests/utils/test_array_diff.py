import numpy as np
import pytest

from generic_grader.utils.array_diff import array_compare, array_diff_details
from generic_grader.utils.mocks import make_mock_function_raise_error

# Test cases for array_diff_details function.


def test_array_diff_details_argwhere_exception(monkeypatch):
    a = np.array([1, 2, 3])
    b = np.array([1, 9, 3])

    # Force argwhere to raise so diff_indices becomes None
    monkeypatch.setattr(np, *make_mock_function_raise_error("argwhere", RuntimeError))

    text = array_diff_details(a, b)
    assert "no differing indices found" in text


def test_array_diff_details_out_of_bounds(monkeypatch):
    a = np.array([1, 2, 3])
    b = np.array([1, 9, 3])

    # Make argwhere return an out-of-bounds index
    monkeypatch.setattr(np, "argwhere", lambda x: np.array([[100]]))

    text = array_diff_details(a, b)
    assert "<out-of-bounds>" in text


def test_array_diff_details_empty_arrays():
    a = np.array([], dtype=float)
    b = np.array([], dtype=float)
    text = array_diff_details(a, b)
    assert "no differing indices found" in text


def test_array_diff_details_float_arrays():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.1])
    text = array_diff_details(a, b)
    # Check that a differing index is reported and shows expected/actual values
    assert "at (2,)" in text
    assert "expected=" in text and "actual=" in text and "3.0" in text and "3.1" in text


def test_array_diff_details_int_arrays():
    a = np.array([1, 2, 3])
    b = np.array([1, 9, 3])
    text = array_diff_details(a, b)
    assert "at (1,)" in text


def test_array_diff_details_propagates(monkeypatch):
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.1])

    # Force array_diff_details to raise
    monkeypatch.setattr(np, *make_mock_function_raise_error("isclose", RuntimeError))

    with pytest.raises(RuntimeError, match="Your program unexpectedly called `isclose"):
        array_diff_details(a, b)


# Test cases for array_compare function.


def test_array_compare_diff_dtype():
    a = np.array([1, 2, 3], dtype=int)
    b = np.array([1, 2, 3], dtype=float)
    equal, details = array_compare(a, b)
    assert not equal
    assert "dtype" in details


def test_array_compare_dtype_access_raises():
    """Test that array_compare handles objects whose dtype attribute raises."""

    class BadDtype:
        @property
        def dtype(self):
            raise RuntimeError("dtype access failed")

        @property
        def shape(self):
            return (3,)

    bad_obj = BadDtype()
    normal_array = np.array([1, 2, 3])

    # When actual has a bad dtype, array_compare should set dtype to None
    # and continue, eventually returning False with details
    equal, details = array_compare(bad_obj, normal_array)
    assert not equal
    assert "dtype=None" in details


def test_array_compare_diff_shape():
    a = np.array([1, 2, 3])
    b = np.array([[1, 2, 5, 3]])
    equal, details = array_compare(a, b)
    assert not equal
    assert "shape" in details


def test_array_compare_shape_access_raises():
    """Test that array_compare handles objects whose shape attribute raises."""

    class BadShape:
        @property
        def dtype(self):
            return float

        @property
        def shape(self):
            raise RuntimeError("shape access failed")

    bad_obj = BadShape()
    normal_array = np.array([1.0, 2.0, 3.0])

    # When actual has a bad shape, array_compare should set shape to None
    # and continue, eventually returning False with details
    equal, details = array_compare(bad_obj, normal_array)
    assert not equal
    assert "shape=None" in details


def test_array_compare_equal_floating():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.0])
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_equal_integer():
    a = np.array([1, 2, 3])
    b = np.array([1, 2, 3])
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_not_equal():
    a = np.array([1, 2, 3])
    b = np.array([1, 9, 3])
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1,)" in details
    assert "actual=" in details and "9" in details
    assert "expected=" in details and "2" in details


def test_array_compare_propagates_allclose(monkeypatch):
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.0001])

    # Force allclose to raise
    monkeypatch.setattr(np, *make_mock_function_raise_error("allclose", RuntimeError))

    try:
        array_compare(a, b)
    except RuntimeError:
        # expected
        return
    raise AssertionError("array_compare did not propagate RuntimeError")


def test_array_compare_propagates_array_equal(monkeypatch):
    """Test that array_compare propagates exceptions from np.array_equal for non-float arrays."""
    a = np.array([1, 2, 3])
    b = np.array([1, 2, 3])

    # Force array_equal to raise
    monkeypatch.setattr(
        np, *make_mock_function_raise_error("array_equal", RuntimeError)
    )

    with pytest.raises(RuntimeError, match="Your program unexpectedly called"):
        array_compare(a, b)


def test_array_compare_tolerance_within_rtol():
    """Test that arrays within relative tolerance are considered equal."""
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.00001, 3.0])
    equal, _ = array_compare(a, b, rtol=1e-4, atol=0.0)
    assert equal


def test_array_compare_tolerance_outside_rtol():
    """Test that arrays outside relative tolerance are not equal."""
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.001, 3.0])
    equal, details = array_compare(a, b, rtol=1e-5, atol=0.0)
    assert not equal
    assert "at (1,)" in details


def test_array_compare_tolerance_within_atol():
    """Test that arrays within absolute tolerance are considered equal."""
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([0.0, 1e-9, 0.0])
    equal, _ = array_compare(a, b, rtol=0.0, atol=1e-8)
    assert equal


def test_array_compare_tolerance_outside_atol():
    """Test that arrays outside absolute tolerance are not equal."""
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([0.0, 1e-6, 0.0])
    equal, details = array_compare(a, b, rtol=0.0, atol=1e-8)
    assert not equal
    assert "at (1,)" in details


def test_array_compare_2d_arrays():
    """Test comparison of 2D arrays."""
    a = np.array([[1, 2], [3, 4]])
    b = np.array([[1, 2], [3, 9]])
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1, 1)" in details
    assert "4" in details and "9" in details


def test_array_compare_3d_arrays():
    """Test comparison of 3D arrays."""
    a = np.ones((2, 3, 4))
    b = np.ones((2, 3, 4))
    b[1, 2, 3] = 999
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1, 2, 3)" in details


def test_array_compare_nan_handling():
    """Test that NaN values are properly detected as differences."""
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, np.nan, 3.0])
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1,)" in details


def test_array_compare_both_nan():
    """Test that NaN in both arrays is handled (numpy considers NaN != NaN)."""
    a = np.array([1.0, np.nan, 3.0])
    b = np.array([1.0, np.nan, 3.0])
    # np.allclose returns False when NaN is present, even if both have NaN
    equal, _ = array_compare(a, b)
    assert not equal  # This is numpy's standard behavior


def test_array_compare_inf_handling():
    """Test comparison with infinity values."""
    a = np.array([1.0, np.inf, 3.0])
    b = np.array([1.0, np.inf, 3.0])
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_inf_mismatch():
    """Test that different infinities are detected."""
    a = np.array([1.0, np.inf, 3.0])
    b = np.array([1.0, -np.inf, 3.0])
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1,)" in details


def test_array_diff_details_max_samples():
    """Test that max_samples limits the number of differences reported."""
    a = np.array([0, 0, 0, 0, 0, 0, 0, 0])
    b = np.array([1, 2, 3, 4, 5, 6, 7, 8])

    text = array_diff_details(a, b, max_samples=3)
    # Should only report first 3 differences
    assert "at (0,)" in text
    assert "at (1,)" in text
    assert "at (2,)" in text
    # Should not report beyond max_samples
    assert "at (4,)" not in text


def test_array_diff_details_single_element():
    """Test diff details for single-element arrays."""
    a = np.array([5])
    b = np.array([10])
    text = array_diff_details(a, b)
    assert "at (0,)" in text
    assert "5" in text and "10" in text


def test_array_compare_single_element():
    """Test comparison of single-element arrays."""
    a = np.array([42])
    b = np.array([42])
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_complex_dtype():
    """Test comparison of complex number arrays."""
    a = np.array([1 + 2j, 3 + 4j])
    b = np.array([1 + 2j, 3 + 4j])
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_complex_dtype_mismatch():
    """Test detection of differences in complex arrays."""
    a = np.array([1 + 2j, 3 + 4j])
    b = np.array([1 + 2j, 3 + 5j])
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1,)" in details


def test_array_compare_structured_array():
    """Test comparison of structured arrays."""
    dt = np.dtype([("x", "i4"), ("y", "f8")])
    a = np.array([(1, 2.0), (3, 4.0)], dtype=dt)
    b = np.array([(1, 2.0), (3, 4.0)], dtype=dt)
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_structured_array_mismatch():
    """Test detection of differences in structured arrays."""
    dt = np.dtype([("x", "i4"), ("y", "f8")])
    a = np.array([(1, 2.0), (3, 4.0)], dtype=dt)
    b = np.array([(1, 2.0), (3, 9.0)], dtype=dt)
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1,)" in details


def test_array_compare_bool_arrays():
    """Test comparison of boolean arrays."""
    a = np.array([True, False, True])
    b = np.array([True, False, True])
    equal, _ = array_compare(a, b)
    assert equal


def test_array_compare_bool_arrays_mismatch():
    """Test detection of differences in boolean arrays."""
    a = np.array([True, False, True])
    b = np.array([True, True, True])
    equal, details = array_compare(a, b)
    assert not equal
    assert "at (1,)" in details


def test_array_diff_details_2d_multiple_diffs():
    """Test that diff details correctly reports multiple differences in 2D arrays."""
    a = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    b = np.array([[1, 99, 3], [4, 5, 88], [7, 77, 9]])

    text = array_diff_details(a, b, max_samples=10)
    # Should report all three differences
    assert "at (0, 1)" in text and "99" in text
    assert "at (1, 2)" in text and "88" in text
    assert "at (2, 1)" in text and "77" in text
