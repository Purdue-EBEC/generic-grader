"""Test the output lines of a function."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str, make_line_range
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test


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

            # Build an error message.
            #
            # Considering adding some fuzziness by only requiring a certain
            # percentage of output to match, but this doesn't work well for very
            # long output.
            line_range = make_line_range(o.start, o.n_lines)
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)

            message = (
                # "\n" + "\n".join(
                #    difflib.ndiff(
                #        actual.split("\n"),
                #        expected.split("\n")
                #    )
                # )
                # + "\n\nHint:\n"
                "\n\nHint:\n"
                + self.wrapper.fill(
                    "Your output did not match the expected output."
                    f"  Double check the formatting of output {line_range}"
                    f" of your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f"  {o.hint}" or "")
                )
                + f"{self.student_user.format_log()}"
            )

            self.maxDiff = None
            self.assertEqual(actual, expected, msg=message)
            # ratio = difflib.SequenceMatcher(None, actual, expected).ratio() #TODO: Figure out why difflb is taking so long - come up with a test case that takes a long time
            # self.assertGreaterEqual(ratio, 0.99, msg=message)

            self.set_score(self, o.weight)  # Full credit

    return TestOutputLinesMatchReference
