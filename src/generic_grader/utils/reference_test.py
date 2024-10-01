"""Test all values in the output from a function."""

import difflib
import functools
import os

from attrs import evolve

from generic_grader.utils.docs import get_wrapper, make_call_str
from generic_grader.utils.exceptions import RefFileNotFoundError
from generic_grader.utils.math_utils import calc_log_limit
from generic_grader.utils.user import RefUser, SubUser

text_wrapper = get_wrapper()


def reference_test(func):
    """Decorator for tests that make comparisons between files produced by a
    reference program and student submitted program.
    """

    @functools.wraps(func)
    def wrapper(self, options):
        o = options

        # Run an optional initialization function.
        if o.init:
            o.init()

        # Make sure the expected output files don't already exist.
        for filename in o.filenames:
            try:
                os.remove(filename)
            except FileNotFoundError:
                pass

        # Create the reference user.
        self.ref_user = RefUser(self, options=o)

        # Run the reference code.
        self.ref_user.call_obj()
        log_limit = calc_log_limit(self.ref_user.log)  # Get log_limit here

        # Rename reference files
        for filename in o.filenames:
            # Silent overwrite if exists.
            try:
                os.replace(filename, f"ref_{filename}")
            except FileNotFoundError:
                raise RefFileNotFoundError(filename)

        sub_o = evolve(o, log_limit=log_limit)

        # Create the student user.
        self.student_user = SubUser(self, options=sub_o)

        # Run the submitted code.
        self.student_user.call_obj()

        # Rename submission files.
        for filename in o.filenames:
            message = ""
            try:
                # Silent overwrite if exists.
                os.replace(filename, f"sub_{filename}")
            except FileNotFoundError:
                call_str = make_call_str(o.obj_name, o.args, o.kwargs)
                self.failureException = FileNotFoundError
                message = (
                    "\n\nHint:\n"
                    + text_wrapper.fill(
                        f"The file `{filename}` was not found.  Make sure your"
                        f" `{o.obj_name}` function creates a file named"
                        f" `{filename}` when called as `{call_str}`"
                        + (o.entries and f" with entries={o.entries}." or ".")
                    )
                    + f"\n\n{self.student_user.format_log()}"
                )
            if message:
                self.fail(message)

        func(self, o)

    return wrapper


def make_diff(actual, expected):
    """Create a diff similar to unittest.TestCase.assertEqual."""

    # Ensure strings end with a newline to make diff readable.
    expected = expected if expected.endswith("\n") else expected + "\n"
    actual = actual if actual.endswith("\n") else actual + "\n"

    return "".join(
        difflib.ndiff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
        )
    )
