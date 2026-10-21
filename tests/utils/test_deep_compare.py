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


def make_self_list(first=1):
    value = [first]
    value.append(value)
    return value


def make_self_dict(first=1):
    value = {"x": first}
    value["self"] = value
    return value


def test_equal_self_containing_lists_pass():
    assert deep_compare(make_self_list(), make_self_list()) == (True, "")


def test_different_self_containing_lists_fail():
    equal, details = deep_compare(make_self_list(1), make_self_list(2))
    assert not equal
    assert "at [0]:" in details


def test_equal_self_containing_dicts_pass():
    assert deep_compare(make_self_dict(), make_self_dict()) == (True, "")


def test_different_self_containing_dicts_fail():
    equal, details = deep_compare(make_self_dict(1.0), make_self_dict(2.0))
    assert not equal
    assert "at ['x']:" in details


def test_self_containing_student_list_against_finite_reference_fails():
    equal, _details = deep_compare(make_self_list(), [1, [1, []]])
    assert not equal


def test_finite_student_list_against_self_containing_reference_fails():
    equal, _details = deep_compare([1, [1, []]], make_self_list())
    assert not equal


def test_mutually_recursive_structures_terminate():
    a, b = [], []
    a.append(b)
    b.append(a)
    c, d = [], []
    c.append(d)
    d.append(c)
    assert deep_compare(a, c) == (True, "")


def test_shared_non_cyclic_substructure_is_compared_each_time():
    shared_actual = [1.0]
    shared_expected = [2.0]
    equal, details = deep_compare(
        [shared_actual, shared_actual], [shared_expected, shared_expected]
    )
    assert not equal
    assert "at [0][0]:" in details
    assert "at [1][0]:" in details


def test_short_string_mismatch_includes_diff_marker():
    equal, details = deep_compare("abc", "abd")
    assert not equal
    assert "expected='abd'" in details
    assert "actual='abc'" in details
    diff_lines = [
        line for line in details.splitlines() if line.lstrip().startswith(("- ", "+ "))
    ]
    assert diff_lines
    assert any("abc" in line for line in diff_lines)
    assert any("abd" in line for line in diff_lines)


def test_multiline_string_mismatch_shows_differing_line_from_both_sides():
    actual_lines = [f"line {i} value {i * 7}" for i in range(1, 13)]
    expected_lines = list(actual_lines)
    expected_lines[5] = "line 6 value 67"  # actual has "line 6 value 42"
    actual = "\n".join(actual_lines) + "\n"
    expected = "\n".join(expected_lines) + "\n"
    assert len(actual) + len(expected) > 350

    equal, details = deep_compare(actual, expected)
    assert not equal
    assert "- line 6 value 42" in details
    assert "+ line 6 value 67" in details


def test_very_long_string_mismatch_reports_without_diff():
    actual = "x" * 1500 + "a" + "y" * 1500
    expected = "x" * 1500 + "b" + "y" * 1500
    equal, details = deep_compare(actual, expected)
    assert not equal
    assert "expected=" in details
    assert "actual=" in details
    assert "- " not in details.split("actual=", 1)[1]


def test_non_str_mismatch_has_no_diff_section():
    equal, details = deep_compare(b"abc", b"abd")
    assert not equal
    assert "expected=b'abd', actual=b'abc'" in details
    assert not any(
        line.lstrip().startswith(("- ", "+ ")) for line in details.splitlines()
    )


def test_huge_int_vs_float_does_not_raise_overflow_error():
    equal, _details = deep_compare(10**400, 1.0, strict_types=False)
    assert equal is False


def test_5000_digit_int_mismatch_reports_without_repr_error():
    equal, details = deep_compare(10**5000, 10**5000 + 1)
    assert not equal
    assert "expected=" in details
    assert "actual=" in details


def test_object_with_raising_class_property_is_type_mismatch():
    class NoClass:
        @property
        def __class__(self):
            raise RuntimeError("no class for you")

    equal, details = deep_compare(NoClass(), 1.0)
    assert equal is False
    assert "expected type float" in details


def _expected_fn():
    return 1


def _actual_fn():
    return 1


class _ExpectedClass:
    pass


class _ActualClass:
    pass


def test_identical_callable_passes():
    assert deep_compare(len, len) == (True, "")
    assert deep_compare(_expected_fn, _expected_fn) == (True, "")
    assert deep_compare(_ExpectedClass, _ExpectedClass) == (True, "")


def test_distinct_functions_report_autograder_misconfiguration():
    equal, details = deep_compare(_actual_fn, _expected_fn)
    assert not equal
    assert "callables cannot be compared by value" in details
    assert "bug in the autograder" in details
    assert "_expected_fn" in details
    assert "_actual_fn" in details
    assert "0x" not in details


def test_distinct_classes_report_autograder_misconfiguration():
    equal, details = deep_compare(_ActualClass, _ExpectedClass)
    assert not equal
    assert "callables cannot be compared by value" in details
    assert "_ExpectedClass" in details
    assert "class_" in details


def test_distinct_builtins_methods_and_partials_report_misconfiguration():
    import functools

    pairs = (
        (abs, len),
        ([].append, [].append),
        (functools.partial(len), functools.partial(len)),
    )
    for actual, expected in pairs:
        equal, details = deep_compare(actual, expected)
        assert not equal
        assert "callables cannot be compared by value" in details


def test_callable_inside_collection_reports_path():
    equal, details = deep_compare({"f": [_actual_fn]}, {"f": [_expected_fn]})
    assert not equal
    assert "at ['f'][0]:" in details
    assert "callables cannot be compared by value" in details


def test_callable_vs_non_callable_is_a_type_mismatch():
    equal, details = deep_compare(1, _expected_fn)
    assert not equal
    assert "expected type function, got int" in details


def test_instance_with_call_method_still_uses_equality():
    class Callable:
        def __call__(self):
            return 1

        def __eq__(self, other):
            return isinstance(other, Callable)

    assert deep_compare(Callable(), Callable())[0]


def test_callable_name_survives_hostile_attributes():
    class Weird(type):
        def __getattribute__(cls, name):
            if name in ("__qualname__", "__module__"):
                raise RuntimeError("no name")
            return super().__getattribute__(name)

    class A(metaclass=Weird):
        pass

    class B(metaclass=Weird):
        pass

    equal, details = deep_compare(A, B)
    assert not equal
    assert "callables cannot be compared by value" in details
