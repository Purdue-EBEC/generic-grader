import glob
import os
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_set_up(options):
    """Create symlinks to the required files that later tests depend on."""
    o = options

    if "" not in sys.path:
        sys.path.insert(0, "")  # pragma: no cover

    if o.init:
        o.init(None, o)

    # Create symlinks to non-globbed form of each required file.
    setup_steps = []
    for file_pattern in o.required_files:
        if "*" not in file_pattern:  # dst will already exist
            continue

        files = glob.glob(file_pattern)

        # Exclude ignored files and existing symlinks so that stale
        # symlinks from a previous run are not counted as matches.
        files = [
            file
            for file in files
            if file not in o.ignored_files and not Path(file).is_symlink()
        ]

        if len(files) == 0:
            warnings.warn(
                f'Cannot find any files matching the pattern "{file_pattern}".',
                stacklevel=3,
            )
            continue

        if len(files) > 1:
            warnings.warn(
                f'Found {len(files)} files matching the pattern "{file_pattern}":'
                f" {files}.  Skipping symlink creation due to ambiguous match.",
                stacklevel=3,
            )
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
