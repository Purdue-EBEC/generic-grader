import os
import sys

import pytest

# `generic_grader` sets this default at import time for the runtime (issue #205);
# setting it here too covers tests that import matplotlib before `generic_grader`.
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
