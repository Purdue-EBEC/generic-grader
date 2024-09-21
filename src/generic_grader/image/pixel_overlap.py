"""Test calculation results."""

import unittest

from parameterized import parameterized
from PIL import Image
from PIL.ImageChops import logical_and

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import make_call_str
from generic_grader.utils.options import options_to_params


def doc_func(func, num, param):
    """Return parameterized docstring when checking output values."""

    o = param.args[0]

    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the {o.region_inner}"
        f" from your `{o.obj_name}` function when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + f" has {o.mode} {o.threshold} pixels"
        + f" in the {o.region_outer}."
    )

    return docstring


def build(options):
    """Build the test class."""

    the_params = options_to_params(options)

    class TestPixelOverlap(unittest.TestCase):
        """A class for functionality tests."""

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_pixel_overlap(self, options):
            """Check if white pixels in black and white images A and B
            overlap the expected amount.
            """

            o = options

            # Run an optional initialization function.  This might be used to
            # create the image files if they don't already exist.
            if o.init:
                o.init(self, options)

            # Get the actual pixel overlap count.
            with Image.open(o.ref_image) as A, Image.open(o.sub_image) as B:
                pixels = sum(logical_and(A, B).getdata()) // 255

            # Test the result.
            if o.mode == "less than":
                message = str(
                    f"\nThe {o.region_inner} has too many pixels"
                    f" in the {o.region_outer}." + (o.hint and f" {o.hint}" or "")
                )
                self.assertLess(pixels, o.threshold, msg=message)

            elif o.mode == "more than":
                message = str(
                    f"\nThe {o.region_inner} does not have enough pixels"
                    f" in the {o.region_outer}." + (o.hint and f" {o.hint}" or "")
                )
                self.assertGreater(pixels, o.threshold, msg=message)

            elif o.mode == "exactly":
                message = str(
                    f"\nThe {o.region_inner} does not have exactly {o.threshold} "
                    f"pixels in the {o.region_outer}." + (o.hint and f" {o.hint}" or "")
                )
                self.assertEqual(pixels, o.threshold, msg=message)

            elif o.mode == "approximately":
                message = str(
                    f"\nThe {o.region_inner} should have approximately {o.threshold} "
                    f"pixels in the {o.region_outer}." + (o.hint and f" {o.hint}" or "")
                )
                self.assertAlmostEqual(pixels, o.threshold, msg=message, delta=o.delta)

            self.set_score(self, options.weight)

    return TestPixelOverlap
