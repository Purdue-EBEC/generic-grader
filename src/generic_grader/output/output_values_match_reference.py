"""Test all values in the output from a function."""

import textwrap
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import make_call_str, ordinalize
from generic_grader.utils.options import Options
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking output values."""

    o = Options()

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the values on output line {o.line_n}"
        f" from your `{o.obj_name}` function when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " match the reference values."
    )

    return docstring


def build(the_params):
    """Create a class for output value tests."""

    class TestOutputValuesMatchReference(unittest.TestCase):
        """A class for formatting tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_output_values_match_reference(self, options):
            """Compare values in the output to reference values."""

            o = options

            # Get the actual and expected values
            actual = self.student_user.get_values()
            expected = self.ref_user.get_values()

            line_nth = ordinalize(o.line_n)
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)

            self.set_score(self, 0)  # No credit

            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    "Your output values did not match the expected values."
                    f"  Double check the values in the {line_nth} output line"
                    f" of your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f"  {o.hint}")
                )
                + f"{self.student_user.format_log()}"
            )

            self.maxDiff = None
            self.assertEqual(actual, expected, msg=message)

            self.set_score(self, o.weight)  # Full credit

    return TestOutputValuesMatchReference
