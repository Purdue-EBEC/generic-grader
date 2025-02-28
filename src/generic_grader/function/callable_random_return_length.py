"""Test the lengths of values returned by a random function."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str
from generic_grader.utils.math_utils import n_trials
from generic_grader.utils.options import options_to_params
from generic_grader.utils.user import SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking the lengths of value(s)
    returned from a function call.
    """
    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        "Check the lengths of value(s) returned from"
        + f" `{o.sub_module}.{o.obj_name}`"
        + f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " matches the expected lengths."
    )

    return docstring


def build(the_options):
    """Build the test class for checking the lengths of values returned from a Callable."""
    the_params = options_to_params(the_options)

    class TestCallableRandomReturnLength(unittest.TestCase):
        """A class for checking the lengths of return values from a Callable."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_return_length(self, options):
            """Check for extra or missing lengths of values returned from a function."""

            o = options

            # Run an optional initialization function.
            if o.init:
                o.init(self, options)

            # Create the student user.
            self.student_user = SubUser(self, o)
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)

            # Collect the actual set by repeated calls to the function.
            actual_set = set()
            trials, max_trials = (
                0,
                n_trials(len(o.expected_set), o.random_chance_tolerance),
            )
            # Stop early if we find extra values
            while trials < max_trials and (actual_set <= o.expected_set):
                trials += 1
                try:
                    actual_set.add(len(self.student_user.call_obj()))
                except TypeError:
                    message = (
                        "\n\nHint:\n"
                        + self.wrapper.fill(
                            f"Your `{o.sub_module}.{o.obj_name}` function when called as `{call_str}`"
                            + (o.entries and f" with entries={o.entries}" or "")
                            + " did not return a value that has a length."
                            + " Make sure your function returns a value that supports"
                            + " the `len()` function."
                        )
                    ) + f"\n\n{self.student_user.format_log()}"
                    self.fail(message)

            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    "The lengths of values returned from your"
                    + f" `{o.sub_module}.{o.obj_name}` function"
                    + f" when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}" or "")
                    + " did not match the expected lengths."
                    + (o.hint and f"  {o.hint}" or "")
                )
                + f"\n\n{self.student_user.format_log()}"
            )
            self.maxDiff = None
            self.assertEqual(actual_set, o.expected_set, msg=message)

            self.set_score(self, o.weight)

    return TestCallableRandomReturnLength
