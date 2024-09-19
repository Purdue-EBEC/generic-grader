"""Test that the lines written to a file match a reference."""

import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str, oxford_list
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking lines in a file."""

    o = param.args[0]

    filenames = [f"`{filename}`" for filename in o.filenames]
    file_s = "file" if len(filenames) == 1 else "files"
    file_list_str = f"{file_s} {oxford_list(filenames)}"
    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check that the lines written to the {file_list_str}"
        f" from your `{o.sub_module}.{o.obj_name}` function"
        f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}" or "")
        + " match the reference."
    )

    return docstring


def build(the_options):
    """Create a class for file line tests."""

    the_params = options_to_params(the_options)

    class TestFileLinesMatchReference(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_file_lines_match_reference(self, options):
            """Check for extra or missing lines in a file."""

            o = options

            if not o.filenames:
                raise ValueError(
                    "There are no files to check."
                    "  This test requires filenames to be specified."
                )

            # Get the actual and expected lines for each file.
            ref_lines, sub_lines = {}, {}
            for filename in o.filenames:
                with open(f"ref_{filename}") as fo:
                    ref_lines[filename] = fo.read().splitlines()
                with open(f"sub_{filename}") as fo:
                    sub_lines[filename] = fo.read().splitlines()

            # Build an error message.
            filenames = [f"`{filename}`" for filename in o.filenames]
            file_s = "file" if len(filenames) == 1 else "files"
            file_list_str = f"{file_s} {oxford_list(filenames)}"
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    f"The lines written to your output {file_s} do not"
                    " match the expected lines."
                    f"  Double check the lines written to the {file_list_str}"
                    f" by your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}." or ".")
                    + (o.hint and f"  {o.hint}" or "")
                )
                + self.student_user.format_log()
            )

            self.maxDiff = None
            self.assertEqual(sub_lines, ref_lines, msg=message)

            self.set_score(self, options.weight)

    return TestFileLinesMatchReference
