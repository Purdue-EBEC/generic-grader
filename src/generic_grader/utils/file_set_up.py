import glob
import os
import shutil
import sys
from contextlib import contextmanager


@contextmanager
def file_set_up(options):
    """Create symlinks to the required files that later tests depend on."""
    o = options

    if "" not in sys.path:
        sys.path.insert(0, "")  # pragma: no cover

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
            shutil.copy(src, dst)

            # Log the symlink for later removal.
            step = {"type": "symlink", "src": src, "dst": dst}
            setup_steps.append(step)
        except FileExistsError:
            pass  # symlink already exists or is unnecessary
    """
    There is a problem, possibly with the way the symlinks are being created, that
    causes any tests that attempt to use the importer class to fail. However, we
    know that the file is being created properly both because the tests that just
    open the file pass, however the tests that use the importer class fail.

    Things that have been tried and confirmed to have failed to resolve the issue:
        1. Using the Path class to create the symlink
        2. Using the os.symlink() function to create the symlink
        3. Using threading.Lock() to ensure that the symlinks are created
        4. Using time.sleep() to ensure that the symlinks are created
        5. Using shutil.copy() to create a copy of the file instead of a symlink

    """

    yield

    # Clean up the symlinks.
    for step in setup_steps:
        os.remove(step["dst"])
