"""Test for presence of required files."""

import glob
import json
import unittest
from pathlib import Path

from parameterized import parameterized

from generic_grader.utils.options import options_to_params


def build(the_options):
    """Create a class to prepare files for other tests."""

    the_params = options_to_params(the_options)

    class TestFileSetUp(unittest.TestCase):
        """A class for file tests."""

        @parameterized.expand(the_params)  # , doc_func=doc_func)
        def test_file_set_up(self, options):
            """Create symlinks to the required files that later tests depend on."""

            o = options

            # Create symlinks to non-globbed form of each required file.
            setup_steps = []
            for file_pattern in o.required_files:
                if "*" not in file_pattern:  # dst will already exist
                    continue

                files = glob.glob(file_pattern)
                files = [file for file in files if file not in o.ignored_files]

                if len(files) != 1:  # src missing or ambiguous
                    continue

                src = files[0]
                dst = file_pattern.replace("*", "")  # deglobbed file pattern
                try:
                    Path.symlink_to(dst, src)

                    # Log the symlink for later removal.
                    step = {"type": "symlink", "src": src, "dst": dst}
                    setup_steps.append(step)
                    with open("setup_steps.json", "w") as file:
                        json.dump(setup_steps, file)
                except FileExistsError:
                    pass  # symlink already exists or is unnecessary

    return TestFileSetUp
