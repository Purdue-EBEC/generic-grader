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
from generic_grader.utils.octave_plot import get_property as get_property_octave
from generic_grader.utils.options import options_to_params
from generic_grader.utils.plot import get_property
from generic_grader.utils.safe_equal import safe_assert_equal
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
                o.init(self, o)

            # Create the reference user.
            self.ref_user = RefUser(self, o)

            # Language dispatch: the Python runtime reads matplotlib's
            # live global state via :func:`plot.get_property`; the
            # Octave runtime captures a JSON sidecar per call and we
            # extract properties from that via
            # :func:`octave_plot.get_property`.  Keeping both paths in
            # this one method (rather than duplicating ``build``)
            # means the parameterization, weighting, and message
            # formatting stay identical across languages.
            is_octave = o.language == "octave"

            # Run the reference code and extract the expected property.
            self.ref_user.call_obj()
            if is_octave:
                expected = get_property_octave(
                    self,
                    self.ref_user.artifacts.get("plot"),
                    o.prop,
                    o.prop_kwargs,
                )
            else:
                expected = get_property(self, o.prop, o.prop_kwargs)
                mpl.pyplot.close()  # Delete the generated figure.

            # Run the submitted code and extract the actual property.
            log_limit = calc_log_limit(self.ref_user.log)
            student_o = evolve(o, log_limit=log_limit)
            self.student_user = SubUser(self, student_o)
            self.student_user.call_obj()
            if is_octave:
                actual = get_property_octave(
                    self,
                    self.student_user.artifacts.get("plot"),
                    o.prop,
                    o.prop_kwargs,
                )
            else:
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
                safe_assert_equal(self, actual, expected, msg=message)

            self.set_score(self, o.weight)

    return TestPlotPropMatchesReference
