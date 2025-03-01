"""Test the range of values returned by a random function."""

import textwrap
import unittest
from math import log10

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import make_call_str
from generic_grader.utils.options import options_to_params
from generic_grader.utils.user import SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking the range of value(s)
    returned from a function call.
    """
    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        "Check the range of value(s) returned from your"
        + f" `{o.sub_module}.{o.obj_name}` function"
        + f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " matches the expected range."
    )

    return docstring


def n_trials(N, tolerance=9):
    """
    For a random variable intended to be distributed uniformly over `N` values,
    return the number of trials necessary to check for extra values with the
    chance of missing an extra value reduced to 1 in 1x10^tolerance.

    The worst case scenario is an off by one error where the function produces
    one number it shouldn't.  E.g. returning 100 when asked for a 2 digit
    number.  The probability p of getting this result is only 1 in 91.  I.e. the
    probability of not getting the bad result (1-p) is 90/91.

    We want to call the function enough times to ensure the chance we will miss
    the bad result is very low (e.g. less than 1 in a billion).

        (1-p)^n < 1e-9

    or

        (90/91)^n < 1e-9

    Solving for n,

        n = ceil( 9 / log10( (N+1) / N) )

    For the 2 digit case mentioned above, this results in only 1,876 calls to
    reduce the probability of missing the extra value to less than 1 in a
    billion.  For the 3 digit case, we require 18,662 calls.
    """
    return int(1 + tolerance / log10((N + 1) / N))


def build(the_options):
    the_params = options_to_params(the_options)

    class TestRandomFuncReturnRange(unittest.TestCase):
        """A class for checking the range of return values from a random function."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_random_func_return_range(self, options):
            """Check for extra or missing values from a function's range."""

            o = options

            # Run an optional initialization function.
            if o.init:
                o.init()

            # Create the student user.
            self.student_user = SubUser(self, o)

            # Collect the actual set by repeated calls to the function.
            actual_set = set()
            trials, max_trials = 0, n_trials(len(o.expected_set))
            # Stop early if we find extra values
            while trials < max_trials and (actual_set <= o.expected_set):
                trials += 1
                actual_set.add(self.student_user.call_obj())

            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    "The range of values returned from your"
                    + f" `{o.sub_module}.{o.obj_name}` function"
                    + f" when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}" or "")
                    + " did not match the expected range."
                    + (o.hint and f"  {o.hint}" or "")
                )
                + f"\n\n{self.student_user.format_log()}"
            )
            self.maxDiff = None
            self.assertEqual(actual_set, o.expected_set, msg=message)

            self.set_score(self, o.weight)  # Full credit

    return TestRandomFuncReturnRange
