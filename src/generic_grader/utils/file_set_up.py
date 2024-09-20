import glob
import os
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_set_up(options):
    """Create symlinks to the required files that later tests depend on."""
    o = options

    if "" not in sys.path:
        sys.path.insert(0, "")  # pragma: no cover

    if o.init:
        o.init()

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
        except FileExistsError:
            pass  # symlink already exists or is unnecessary

    yield

    # Clean up the symlinks.
    for step in setup_steps:
        os.remove(step["dst"])
