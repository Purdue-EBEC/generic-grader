"""Test for appropriate program length."""

import textwrap
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.static import get_tokens


def build(the_params):
    """Create a class for program length tests."""

    class TestProgramLength(unittest.TestCase):
        """A class for program length check."""

        # TODO: enable partial credit when program is only a little too long
        @parameterized.expand(the_params)
        @weighted
        def test_program_length(self, options):
            """Check if the program is well bigger than expected."""

            actual = len(get_tokens(self, options.sub_module + ".py"))
            expected = len(get_tokens(self, options.ref_module + ".py"))

            self.set_score(self, 0)  # No credit
            maximum = int(2 * expected)
            message = "\n\nHint:\n" + textwrap.fill(
                "Your program is a lot bigger than expected."
                "  See if you can redesign it to use less code."
            )
            self.assertLessEqual(actual, maximum, msg=message)

            self.set_score(self, options.weight)  # Full credit.
            maximum = int(1.5 * expected)
            message = "\n\nHint:\n" + textwrap.fill(
                "Your program is a bit bigger than expected."
                "  See if you can redesign it to use less code."
            )
            self.assertLessEqual(actual, maximum, msg=message)

    return TestProgramLength