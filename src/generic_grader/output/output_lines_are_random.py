"""Test that a function's output lines are random."""

import textwrap
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import make_call_str, make_line_range
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test
from generic_grader.utils.user import RefUser, SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking randomness of values in a
    file."""

    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        "Check that the lines of output"
        + f" from your `{o.sub_module}.{o.obj_name}` function"
        + f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " are random."
    )

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestOutputLinesAreRandom(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_output_lines_are_random(self, options):
            """Check that the output lines change from one run to the next."""

            o = options

            # Run an optional initialization function.
            if o.init:
                o.init()

            # Create the reference and two student users.
            self.ref_user = RefUser(self, o)
            self.student_user_1 = SubUser(self, o)
            self.student_user_2 = SubUser(self, o)

            # Run the reference and submitted code.
            self.ref_user.call_obj()
            self.student_user_1.call_obj()
            self.student_user_2.call_obj()

            # Get the output.
            first = self.student_user_1.read_log()
            second = self.student_user_2.read_log()

            # Build an error message.
            line_range = make_line_range(o.start, o.n_lines)
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)

            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    "Your output does not appear to be random."
                    f"  Double check that the output on {line_range}"
                    f" of your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}" or "")
                    + " is random."
                    + (o.hint and f"  {o.hint}" or "")
                )
                + f"{self.student_user.format_log()}"
            )

            self.maxDiff = None
            self.assertNotEqual(first, second, msg=message)

            self.set_score(self, o.weight)  # Full credit

    return TestOutputLinesAreRandom
