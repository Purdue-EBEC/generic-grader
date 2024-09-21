"""Test calculation results."""

import difflib
import unittest

import pytesseract
from parameterized import parameterized
from PIL import Image

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.options import options_to_params


def doc_func(func, num, param):
    """Return parameterized docstring when checking a turtle path."""

    o = param.args[0]

    docstring = f'Check the drawing for the words: "{o.expected_words}".'

    return docstring


def build(options):
    """Create the OCRWordsMatchReference test class"""

    the_params = options_to_params(options)

    class OCRWordsMatchReference(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        def test_ocr_words_match_reference(self, options):
            """Check if the OCR characters from the student's submission match the
            reference solution.
            """

            o = options
            expected_words = o.expected_words
            # Run an optional initialization function.  This might be used to
            # create the image files if they don't already exist.
            if o.init:
                o.init(self, options)

            # Open the solution image and convert it to a string.
            with Image.open("sol.png") as sol_image:
                actual_words = pytesseract.image_to_string(sol_image)

            actual_words = [f"{w}\n" for w in actual_words.lower().strip().split()]
            expected_words = [f"{w}\n" for w in expected_words.lower().strip().split()]
            message = (
                "\n"
                + "".join(difflib.ndiff(actual_words, expected_words))
                + "\n\nHint:\n"
                + self.wrapper.fill(
                    "The words found in your solution are not sufficiently similar"
                    " to the expected words." + (o.hint and f"  {o.hint}" or "")
                )
            )
            ratio = difflib.SequenceMatcher(
                None,
                "".join(actual_words),
                "".join(expected_words),
            ).ratio()
            self.assertGreaterEqual(ratio, o.ratio, msg=message)
            self.set_score(self, options.weight)

    return OCRWordsMatchReference
