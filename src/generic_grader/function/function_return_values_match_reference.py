"""Test calculation results."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking value(s) returned from a
    function call.
    """

    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the value(s) returned"
        f" from your `{o.sub_module}.{o.obj_name}` function when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " match the reference value(s)."
    )

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestFunctionReturnValuesMatchReference(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_function_return_values_match_reference(self, options):
            """Compare function return values to a reference."""

            o = options

            # Get the actual and expected values
            actual = self.student_user.returned_values
            expected = self.ref_user.returned_values

            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            formatted_log = self.student_user.format_log()
            expected_type = type(expected)

            type_msg = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Your `{o.obj_name}` function"
                    f" returned a(n) {type(actual).__name__},"
                    f" but a(n) {expected_type.__name__} was expected."
                    "  Double check the type of the value(s) returned"
                    f" from your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f"  {o.hint}")
                )
                + f"{formatted_log}"
            )

            value_msg = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Your `{o.obj_name}` function's return value(s)"
                    " did not match the expected return value(s)."
                    "  Double check the value(s) returned"
                    f" from your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f"  {o.hint}")
                )
                + f"{formatted_log}"
            )

            self.maxDiff = None
            self.assertIsInstance(actual, expected_type, msg=type_msg)
            if isinstance(expected, float):
                self.assertAlmostEqual(actual, expected, msg=value_msg)
            else:
                self.assertEqual(actual, expected, msg=value_msg)

            self.set_score(self, o.weight)  # Full credit

    return TestFunctionReturnValuesMatchReference
