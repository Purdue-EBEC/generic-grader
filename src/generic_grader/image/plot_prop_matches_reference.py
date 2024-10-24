"""Test that the properties of a plot match a reference."""

import unittest

import matplotlib as mpl
import numpy as np
from attrs import evolve
from parameterized import parameterized
from rapidfuzz.distance.Levenshtein import normalized_similarity

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str
from generic_grader.utils.math_utils import calc_log_limit
from generic_grader.utils.options import options_to_params
from generic_grader.utils.plot import get_property
from generic_grader.utils.user import RefUser, SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking the properties of a
    plot."""

    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the {o.prop} in the plot generated"
        f" from your `{o.obj_name}` function when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " matches the reference."
    )

    return docstring


def build(the_options):
    the_params = options_to_params(the_options)

    class TestPlotPropMatchesReference(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_plot_prop_matches_reference(self, options):
            """Check that the properties of a plot match a reference."""

            o = options

            # Run an optional initialization function.
            if o.init:
                o.init()

            # Create the reference user.
            self.ref_user = RefUser(self, o)

            # Run the reference code and extract the expected property.
            self.ref_user.call_obj()
            expected = get_property(self, o.prop, o.prop_kwargs)
            mpl.pyplot.close()  # Delete the generated figure.

            # Run the submitted code and extract the actual property.
            log_limit = calc_log_limit(self.ref_user.log)
            student_o = evolve(o, log_limit=log_limit)
            self.student_user = SubUser(self, student_o)
            self.student_user.call_obj()
            actual = get_property(self, o.prop, o.prop_kwargs)
            mpl.pyplot.close()  # Delete the generated figure.

            # Build an error message.
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    "Your plot did not match the expected plot."
                    f"  Double check the {o.prop} in the plot produced by"
                    f" your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (
                        o.ratio < 1
                        and "  The words found in your solution are not"
                        " sufficiently similar to the expected words."
                        or ""
                    )
                    + (o.hint and f"  {o.hint}" or "")
                )
                + f"{self.student_user.format_log()}"
            )

            self.maxDiff = None
            if o.prop == "xy data":
                error = np.sqrt(
                    np.mean(
                        np.square(
                            expected.y - np.interp(expected.x, actual.x, actual.y)
                        )
                    )
                )
                self.assertAlmostEqual(error, 0, msg=message, delta=0.01)
            elif isinstance(expected, str) and o.ratio < 1:
                ratio = normalized_similarity(actual, expected)
                self.assertGreaterEqual(ratio, o.ratio, msg=message)
            else:
                self.assertEqual(actual, expected, msg=message)

            self.set_score(self, o.weight)

    return TestPlotPropMatchesReference
