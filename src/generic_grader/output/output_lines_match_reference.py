"""Test the output lines of a function."""

import unittest

from parameterized import parameterized
from rapidfuzz import fuzz

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str, make_line_range
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test
from generic_grader.utils.safe_equal import safe_assert_equal


def doc_func(func, num, param):
    """Return parameterized docstring when checking formatting of output lines."""

    o = param.args[0]

    line_range = make_line_range(o.start, o.n_lines)
    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the formatting of output {line_range}"
        f" from your `{o.obj_name}` function when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " matches the reference formatting."
    )

    return docstring


def build(the_options):
    """Create a class for output line tests."""

    the_params = options_to_params(the_options)

    class TestOutputLinesMatchReference(unittest.TestCase):
        """A class for formatting tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_output_lines_match_reference(self, options):
            """Compare lines in the output log to reference log."""

            o = options

            # Get the actual and expected values.
            actual = self.student_user.read_log()
            expected = self.ref_user.read_log()

            line_range = make_line_range(o.start, o.n_lines)
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)

            if o.ratio < 1:
                # Use rapidfuzz for partial matching (avoids O(n²) difflib).
                similarity = fuzz.ratio(actual, expected) / 100
                message = (
                    "\n\nHint:\n"
                    + self.wrapper.fill(
                        "Your output is not sufficiently similar to the"
                        " expected output."
                        f"  Double check the formatting of output {line_range}"
                        f" of your `{o.obj_name}` function when called as"
                        f" `{call_str}`"
                        + (o.entries and f" with entries={o.entries}." or ".")
                        + (o.hint and f"  {o.hint}" or "")
                    )
                    + f"{self.student_user.format_log()}"
                )
                self.assertGreaterEqual(similarity, o.ratio, msg=message)
            else:
                # Exact match (default).
                message = (
                    "\n\nHint:\n"
                    + self.wrapper.fill(
                        "Your output did not match the expected output."
                        f"  Double check the formatting of output {line_range}"
                        f" of your `{o.obj_name}` function when called as"
                        f" `{call_str}`"
                        + (o.entries and f" with entries={o.entries}." or ".")
                        + (o.hint and f"  {o.hint}" or "")
                    )
                    + f"{self.student_user.format_log()}"
                )
                safe_assert_equal(self, actual, expected, msg=message)

            self.set_score(self, o.weight)  # Full credit

    return TestOutputLinesMatchReference
