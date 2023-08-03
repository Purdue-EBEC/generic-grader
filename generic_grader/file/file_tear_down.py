import json
import os
import unittest


def build():
    """Create a class to clean up after the test suite is run."""

    class TestFileTearDown(unittest.TestCase):
        """A class to undo the set up."""

        def test_file_tear_down(self):
            """Undo the file setup."""

            setup_log = json.load(open("setup_log.json"))

            # Iterate through the setup log, undoing each step.
            for step in reversed(setup_log):
                if step["type"] == "symlink":
                    os.remove(step["dst"])
                elif step["type"] == "file":
                    os.remove(step["file"])
                elif step["type"] == "dir":
                    os.rmdir(step["dir"])
                else:
                    raise ValueError("Unknown step type: " + step["type"])

    return TestFileTearDown
