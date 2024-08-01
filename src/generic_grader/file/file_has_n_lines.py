"""Test the number of lines in a file."""

import textwrap
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import make_call_str, oxford_list
from generic_grader.utils.reference_test import reference_test


def doc_func(func, num, param):
    """Return parameterized docstring when checking the length of a file."""

    o = param.args[0]

    filenames = [f"`{filename}`" for filename in o.filenames]
    file_s = "file" if len(filenames) == 1 else "files"
    file_list_str = f"{file_s} {oxford_list(filenames)}"
    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
    docstring = (
        f"Check the number of lines written to the {file_list_str}"
        f" from your `{o.sub_module}.{o.obj_name}` function"
        f" when called as `{call_str}`"
        + (o.entries and f" with entries={o.entries}." or ".")
    )

    return docstring


def build(the_params):
    """A class for file length tests."""

    class TestFileHasNLines(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_file_has_n_lines(self, options):
            """Check for the expected number of lines in a file."""

            o = options

            # Get the actual and expected values.
            ref_files, sub_files = [], []
            for filename in o.filenames:
                with open(f"ref_{filename}") as fo:
                    ref_files.append(fo.read())
                with open(f"sub_{filename}") as fo:
                    sub_files.append(fo.read())

            expected = [len(string.splitlines()) for string in ref_files]
            actual = [len(string.splitlines()) for string in sub_files]

            # Build an error message.
            filenames = [f"`{filename}`" for filename in o.filenames]
            file_s = "file" if len(filenames) == 1 else "files"
            files_do = file_s + (" does" if len(filenames) == 1 else " do")
            file_list_str = f"{file_s} {oxford_list(filenames)}"
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Your output {files_do} not have the expected number of lines."
                    f"  Double check the number of lines written to the {file_list_str}"
                    f" by your `{o.obj_name}` function when called as `{call_str}`"
                    + (" with entries={o.entries}." if o.entries else ".")
                    + (f"  {o.hint}" if o.hint else "")
                )
                + self.student_user.format_log()
            )

            self.maxDiff = None
            self.assertEqual(actual, expected, msg=message)

    return TestFileHasNLines
