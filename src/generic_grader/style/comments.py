"""Test for appropriate comment length."""

import os
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.options import options_to_params
from generic_grader.utils.static import get_comments


def doc_func(func, num, param):
    """Return docstring when checking comments."""

    return "Check if the program is well commented."


def build(the_options):
    """Create a class for comment length tests."""

    the_params = options_to_params(the_options)

    class TestCommentLength(unittest.TestCase):
        """A class for comment length check."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_comment_length(self, options):
            """Check if the program is well commented."""

            submission_file = options.sub_module.replace(".", os.path.sep) + ".py"
            _, actual_body_comments = get_comments(self, submission_file)
            actual = sum([len(c) for c in actual_body_comments])

            reference_file = options.ref_module.replace(".", os.path.sep) + ".py"
            _, ref_body_comments = get_comments(self, reference_file)
            expected = sum([len(c) for c in ref_body_comments])

            minimum = max(int(0.5 * expected), 10)  # Require at least 10 characters.
            message = "\n\nHint:\n" + self.wrapper.fill(
                "Your program has too few comments."
                "  Add more comments to better explain your code."
            )
            self.assertGreaterEqual(actual, minimum, msg=message)

            maximum = max(int(5 * expected), 100)  # Always allow up to 100 characters.
            message = "\n\nHint:\n" + self.wrapper.fill(
                "Your program has a lot of comments."
                "  See if you can make your comments more concise."
            )
            self.assertLessEqual(actual, maximum, msg=message)
            self.set_score(self, options.weight)

    return TestCommentLength
