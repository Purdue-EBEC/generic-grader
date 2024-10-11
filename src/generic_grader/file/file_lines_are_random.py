"""Test that the values written to a file are random."""

import os
import unittest

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper, make_call_str, oxford_list
from generic_grader.utils.options import options_to_params
from generic_grader.utils.reference_test import reference_test
from generic_grader.utils.user import SubUser


def doc_func(func, num, param):
    """Return parameterized docstring when checking randomness of values in a
    file."""

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
        + " are random."
    )

    return docstring


def build(options):
    """Create a class to test that file lines are random."""

    the_params = options_to_params(options)

    class TestFileLinesAreRandom(unittest.TestCase):
        """A class for functionality tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=doc_func)
        @weighted
        @reference_test
        def test_file_lines_are_random(self, options):
            """Check that the lines written to a file change from one run to the
            next."""

            o = options

            if not o.filenames:
                raise ValueError(
                    "There are no files to check."
                    "  This test requires filenames to be specified."
                )

            # Get the first set of values.
            first_files = []
            for filename in o.filenames:
                with open(f"sub_{filename}") as fo:
                    first_files.append(fo.read())

            # Create new user and re-run the submitted code.
            self.student_user_2 = SubUser(self, o)
            self.student_user_2.call_obj()
            message = ""
            for filename in o.filenames:
                try:
                    # Silent overwrite if exists.
                    os.replace(filename, f"sub_{filename}")
                except FileNotFoundError:
                    # This error can only occur if the user does not create the file every time.
                    self.failureException = FileNotFoundError
                    call_str = make_call_str(o.obj_name, o.args, o.kwargs)
                    message = (
                        "\n\nHint:\n"
                        + self.wrapper.fill(
                            f"The file `{filename}` was not found.  Make sure your"
                            f" `{o.obj_name}` function creates a file named"
                            f" `{filename}` when called as `{call_str}` every time it runs"
                            + (o.entries and f" with entries={o.entries}." or ".")
                        )
                        + f"\n\n{self.student_user_2.format_log()}"
                    )
                if message:
                    self.fail(message)

            # Get the second set of values.
            second_files = []
            for filename in o.filenames:
                with open(f"sub_{filename}") as fo:
                    second_files.append(fo.read())

            # Build an error message.
            filenames = [f"`{filename}`" for filename in o.filenames]
            file_s = "file" if len(filenames) == 1 else "files"
            files_do = file_s + (" does" if len(filenames) == 1 else " do")
            file_list_str = f"{file_s} {oxford_list(filenames)}"
            call_str = make_call_str(o.obj_name, o.args, o.kwargs)
            message = (
                "\n\nHint:\n"
                + self.wrapper.fill(
                    f"Your output {files_do} not appear to be random."
                    f"  Double check that the values written to the {file_list_str}"
                    f" by your `{o.obj_name}` function when called as `{call_str}`"
                    + (o.entries and f" with entries={o.entries}" or "")
                    + " are random."
                    + (o.hint and f"  {o.hint}" or "")
                )
                + self.student_user.format_log()
            )

            self.maxDiff = None
            self.assertNotEqual(first_files, second_files, msg=message)
            self.set_score(self, options.weight)

    return TestFileLinesAreRandom
