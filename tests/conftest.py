import os
import sys

import pytest

# Force a non-interactive matplotlib backend for the whole test suite.  CI runs
# under Xvfb with DISPLAY set, so matplotlib's default backend is Tk; its
# first-use initialization (``tk.Tk(...)``) can exceed the 1-second
# ``Options.time_limit`` enforced by
# ``generic_grader.utils.resource_limits.time_limit``.  That made the first
# plotting case flake with ``UserTimeoutError`` (see issue #205).  Agg never
# opens a display, so the Tk cost is removed entirely.  ``setdefault`` lets a
# developer select a different non-interactive backend; an interactive backend
# is rejected by ``tests/test_matplotlib_backend.py``.
os.environ.setdefault("MPLBACKEND", "Agg")


@pytest.fixture(scope="function")
def fix_syspath(tmp_path):
    """
    This is the current solution to the empty string being missing
    from sys.path when running pytest."""
    old_path = sys.path.copy()
    old_dir = os.getcwd()
    old_modules = dict(sys.modules)
    sys.path.insert(0, "")
    os.chdir(tmp_path)
    yield tmp_path
    for module in list(sys.modules):
        if module not in old_modules:
            del sys.modules[module]
    sys.path = old_path
    os.chdir(old_dir)
