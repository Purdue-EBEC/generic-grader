"""Test for appropriate program length."""

import os
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.options import options_to_params
from generic_grader.utils.static import get_tokens


def doc_func(func, num, param):
    """Return docstring when checking program length."""

    return "Check if the program is bigger than expected."


def build(the_options):
    """Create a class for program length tests."""

    the_params = options_to_params(the_options)

    class TestProgramLength(unittest.TestCase):
        """A class for program length check."""

        wrapper = get_wrapper()

        # TODO: enable partial credit when program is only a little too long
        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_program_length(self, options):
            """Check if the program is bigger than expected."""

            submission_file = options.sub_module.replace(".", os.path.sep) + ".py"
            actual = len(get_tokens(self, submission_file))

            reference_file = options.ref_module.replace(".", os.path.sep) + ".py"
            expected = len(get_tokens(self, reference_file))

            maximum = int(2 * expected)
            message = "\n\nHint:\n" + self.wrapper.fill(
                "Your program is a lot bigger than expected."
                "  See if you can redesign it to use less code."
            )
            self.assertLessEqual(actual, maximum, msg=message)

            self.set_score(self, options.weight)  # Full credit.
            maximum = int(1.5 * expected)
            message = "\n\nHint:\n" + self.wrapper.fill(
                "Your program is a bit bigger than expected."
                "  See if you can redesign it to use less code."
            )
            self.assertLessEqual(actual, maximum, msg=message)

    return TestProgramLength
