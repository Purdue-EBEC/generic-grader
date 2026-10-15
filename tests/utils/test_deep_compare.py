import numpy as np
import pytest

from generic_grader.utils.deep_compare import deep_compare


def test_reported_gradescope_tuple_passes():
    actual = (31.999999999999996, 91.84322033898306, 236.0)
    expected = (32.00000000000001, 91.84322033898306, 236.0)
    assert deep_compare(actual, expected) == (True, "")


def test_equal_values_return_empty_details():
    assert deep_compare([1, 2.5, "a", (None, True)], [1, 2.5, "a", (None, True)]) == (
        True,
        "",
    )


def test_float_outside_tolerance_fails_with_message():
    equal, details = deep_compare([1.0, 2.1], [1.0, 2.0])
    assert not equal
    assert details.startswith("\nDetails: at [1]:")
    assert "2.1 != 2.0 within" in details
    assert "difference)" in details


def test_tolerance_options_are_honoured():
    assert deep_compare([3.05], [3.0], rtol=0.1)[0]
    assert deep_compare([3.5], [3.0], rtol=0.0, atol=1.0)[0]
    assert not deep_compare([3.00000001], [3.0], rtol=1e-10)[0]


def test_nan_equals_nan_and_inf_equals_inf():
    assert deep_compare((float("nan"), float("inf")), (float("nan"), float("inf")))[0]
    assert not deep_compare((float("nan"),), (1.0,))[0]
    assert not deep_compare((float("-inf"),), (float("inf"),))[0]
    assert not deep_compare((1.0,), (float("inf"),))[0]
    assert not deep_compare((float("inf"),), (1.0,))[0]


def test_integers_compare_exactly():
    assert not deep_compare([1_000_000_001], [1_000_000_000])[0]


def test_nested_path_is_reported():
    actual = {"a": [1, (2.0, 3.5)]}
    expected = {"a": [1, (2.0, 3.0)]}
    equal, details = deep_compare(actual, expected)
    assert not equal
    assert "at ['a'][1][1]:" in details


def test_top_level_failure_names_top_level():
    equal, details = deep_compare("abc", "abd")
    assert not equal
    assert "at top level:" in details
    assert "expected='abd', actual='abc'" in details


def test_sequence_length_mismatch():
    equal, details = deep_compare([1, 2], [1, 2, 3])
    assert not equal
    assert "expected length 3, got 2" in details


def test_dict_key_order_is_ignored():
    assert deep_compare({"a": 1.0, "b": 2.0}, {"b": 2.0, "a": 1.0})[0]


def test_dict_missing_and_extra_keys():
    equal, details = deep_compare({"a": 1, "c": 3}, {"a": 1, "b": 2})
    assert not equal
    assert "missing keys ['b']" in details
    assert "extra keys ['c']" in details


def test_dict_value_tolerance():
    assert deep_compare({"b": 2.00000000001}, {"b": 2.0})[0]


def test_sets_use_exact_equality():
    assert deep_compare({1, 2}, {2, 1})[0]
    assert not deep_compare({1, 2}, {1, 3})[0]


def test_array_inside_collections_uses_tolerance():
    actual = {"a": (np.array([1.0, 2.0 + 1e-12]),)}
    expected = {"a": (np.array([1.0, 2.0]),)}
    assert deep_compare(actual, expected)[0]


def test_array_difference_reports_path():
    actual = [np.array([1, 2, 4])]
    expected = [np.array([1, 2, 3])]
    equal, details = deep_compare(actual, expected)
    assert not equal
    assert "at [0]:" in details
    assert "at (2,)" in details
    assert "actual=" in details


def test_array_shape_difference_reports_shape():
    equal, details = deep_compare(np.zeros((2, 2)), np.zeros((4,)))
    assert not equal
    assert "shapes differ" in details


def test_numpy_exceptions_propagate(monkeypatch):
    def raise_error(*args, **kwargs):
        raise RuntimeError("comparison failed")

    monkeypatch.setattr(np, "allclose", raise_error)
    with pytest.raises(RuntimeError):
        deep_compare(np.array([1.0]), np.array([1.0]))


def test_strict_types_reject_container_and_number_mismatches():
    for actual, expected, text in (
        ((1, 2), [1, 2], "expected type list, got tuple"),
        ([1], [1.0], "expected type float, got int"),
        (3.0, np.float64(3.0), "expected type float64, got float"),
    ):
        equal, details = deep_compare(actual, expected)
        assert not equal
        assert text in details


def test_subclass_of_expected_type_passes_strict_check():
    assert deep_compare(np.float64(3.0), 3.0)[0]


def test_relaxed_types_accept_int_for_float_but_not_container_swap():
    assert deep_compare(3, 3.0, strict_types=False)[0]
    assert deep_compare([3, 4.0], [3.0, 4], strict_types=False)[0]
    assert not deep_compare((3,), [3], strict_types=False)[0]
    assert not deep_compare("3", 3.0, strict_types=False)[0]


def test_bool_is_not_a_real_number():
    assert not deep_compare(1, True)[0]
    assert deep_compare(True, True)[0]


def test_max_samples_limits_reported_failures():
    equal, details = deep_compare(
        list(range(10)), [x + 100 for x in range(10)], max_samples=3
    )
    assert not equal
    assert details.count("at [") == 3


def test_object_whose_equality_raises_is_a_mismatch():
    class Boom:
        def __eq__(self, other):
            raise RuntimeError("boom")

    equal, details = deep_compare([Boom()], [Boom()])
    assert not equal
    assert "at [0]:" in details
