"""Test for presence of required files."""

import glob
import os
import textwrap
import unittest

from gradescope_utils.autograder_utils.decorators import weight
from parameterized import parameterized

# from tests.config import SUB_MODULE, REQUIRED_FILES, IGNORED_FILES

# The prep() function is intended to run once before any tests are run.  It is
# typically used to create solution image files for drawing exercises.  See
# 05/2/Spiral.Octagon/tests/config.py for an example.  The prep() function is
# called here, because so far has always been the first test.  Unittest, loads
# this test, then it imports from config.py.  Once the configuration is isolated
# from the tests, this should be moved to the exercise configuration.

# try:
#     # Run exercise specific test preparation steps if available.
#     from tests.config import prep
#
#     prep()
# except ImportError:
#     pass


def build(the_params):
    """Create a class for file presence tests."""

    class TestFilePresence(unittest.TestCase):
        """A class for file tests."""

        wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ")

        @parameterized.expand(the_params)  # , doc_func=doc_func)
        @weight(0)
        def test_submitted_files(self, options):
            # def test_submitted_files(self, options):
            """Check for submission of required files."""

            o = options

            # Remove the symlink if it exists.
            link_file = o.sub_module + ".py"
            if os.path.islink(link_file):
                os.remove(link_file)

            ignored_files, missing_files, extra_files, error_msg = [], [], [], ""

            # Collect a list of files to ignore.
            for file_pattern in o.ignored_files:
                ignored_files.extend(glob.glob(file_pattern))

            for file_pattern in o.required_files:
                # Create a list of all files matching the pattern.
                files = glob.glob(file_pattern)
                # Remove any ignored_files from the list.
                files = list(filter(lambda x: x not in ignored_files, files))
                n_files = len(files)

                if n_files < 1:  # Can't find required file
                    missing_files.append(file_pattern)
                elif n_files > 1:  # Found too many files matching this pattern
                    extra_files.append(file_pattern)
                else:
                    # Create a symlink to the file matching the pattern
                    # with the same name, but minus the username suffix.
                    src = files[0]  # The only file found.
                    dst = file_pattern.replace("*", "")  # deglobbed file pattern
                    if src != dst:
                        try:
                            os.symlink(src, dst)
                        except FileExistsError:
                            error_msg += (
                                f"The file {dst}"
                                + " is missing the required suffix"
                                + " (typically your username)."
                            )

            for file_pattern in missing_files:
                error_msg += (
                    "Cannot find any files"
                    f' matching the pattern "{file_pattern}".'
                    "  Make sure that you have included a file"
                    " with a name matching this pattern in your submission."
                )

            for file_pattern in extra_files:
                error_msg += (
                    "Submission contains too many files"
                    f' matching the pattern "{file_pattern}".'
                    "   Make sure that you have included exactly one file"
                    " with a name matching this pattern in your submission."
                )

            if error_msg:
                self.fail("\n\nHint:\n" + self.wrapper.fill(error_msg))
            print("Found all required files.")

    return TestFilePresence
