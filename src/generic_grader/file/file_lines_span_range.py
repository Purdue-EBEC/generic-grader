"""Test the range of random values that are written to a file."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str, oxford_list
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking range of random numbers
    written to a file.
    """

    o = param.args[0]

    filenames = [f"`{filename}`" for filename in o.filenames]
    file_s = "file" if len(filenames) == 1 else "files"
    file_list_str = f"{file_s} {oxford_list(filenames)}"
    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the range of values written to the {file_list_str}"
        f" from your `{o.sub_module}.{o.obj_name}` function"
        f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " spans the expected range."
    )

    return docstring


def build(options):
    """A class for file value range tests."""

    the_params = options_to_params(options)

    class TestFileLinesSpanRange(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_lines_span_range(self, options):
            """Check for extra or missing random values in a file's lines."""

            o = options

            # Get the actual and expected values.
            ref_sets, sub_sets = [], []
            for filename in o.filenames:
                with open(f"ref_{filename}") as fo:
                    ref_sets.append(set(fo.read().splitlines()))
                with open(f"sub_{filename}") as fo:
                    sub_sets.append(set(fo.read().splitlines()))

            # Build an error message.
            filenames = [f"`{filename}`" for filename in o.filenames]
            file_s = "file" if len(filenames) == 1 else "files"
            file_list_str = f"{file_s} {oxford_list(filenames)}"
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    f"The values written to your output {file_s} do not"
                    " span the expected set of values."
                    f"  Double check the values written to the {file_list_str}"
                    f" by your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f"  {o.hint}" or "")
                )
                + self.student_user.format_log()
            )

            self.maxDiff = None
            self.assertEqual(sub_sets, ref_sets, msg=message)
            self.set_score(self, options.weight)

    return TestFileLinesSpanRange
