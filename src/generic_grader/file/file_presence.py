"""Test for presence of required files."""

import glob
import unittest
from pathlib import Path

from parameterized import parameterized

from generic_grader.utils.decorators import weighted
from generic_grader.utils.docs import get_wrapper
from generic_grader.utils.options import options_to_params

# TODO
# The prep() function is intended to run once before any tests are run.  It is
# typically used to create solution image files for drawing exercises.  See
# 05/2/Spiral.Octagon/tests/config.py for an example.  The prep() function was
# called here, because so far has always been the first test.  Unittest, loads
# this test, then it imports from config.py.  It doesn't make any sense to run
# one off prep() functions in a generalized testing package, so this should be
# moved to the exercise's configuration.

# try:
#     # Run exercise specific test preparation steps if available.
#     from tests.config import prep
#
#     prep()
# except ImportError:
#     pass


# TODO
# Move the test_submitted_files() function out of the class and into the module
# scope.  Then assign the function to an attribute of the class.  This will make
# the code more readable (less indentation).


def build(the_options):
    """Create a class for file presence tests."""

    the_params = options_to_params(the_options)

    class TestFilePresence(unittest.TestCase):
        """A class for file tests."""

        wrapper = get_wrapper()

        @parameterized.expand(the_params, doc_func=lambda func, n, p: func.__doc__)
        @weighted
        def test_submitted_files(self, options):
            """Check for submission of required files."""

            o = options

            ignored_files, errors = [], []

            # Collect a list of files to ignore.
            for file_pattern in o.ignored_files:
                ignored_files.extend(glob.glob(file_pattern))

            for file_pattern in o.required_files:
                # Create a list of all files matching the pattern.
                files = glob.glob(file_pattern)

                # Remove ignored_files and symlinks from the list.
                files = [
                    file
                    for file in files
                    if file not in ignored_files and not Path(file).is_symlink()
                ]

                match len(files):
                    case 0:  # Can't find a required file
                        errors.append(
                            "Cannot find any files"
                            f' matching the pattern "{file_pattern}".'
                            "  Make sure that you have included a file"
                            " with a name matching this pattern in your submission."
                        )
                    case 1:  # Found exactly one matching file. This is good.
                        file = files[0]
                        if file == file_pattern.replace("*", ""):  # Missing "_login"
                            errors.append(
                                f'The file "{file}" does not meet'
                                + " this exercise's file naming requirements."
                                + "  Make sure you have included your login"
                                + " at the end of the file's name."
                            )
                    case _:  # Found too many files matching this pattern
                        errors.append(
                            "Your submission contains too many files"
                            f' matching the pattern "{file_pattern}".'
                            "  Make sure that you have included exactly one file"
                            " with a name matching this pattern."
                        )

            if errors:
                self.fail("\n\nHint:\n" + self.wrapper.fill("  ".join(errors)))
            print("Found all required files.")
            self.set_score(self, o.weight)  # Full credit.

    return TestFilePresence
