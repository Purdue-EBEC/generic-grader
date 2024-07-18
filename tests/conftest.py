import os
import sys

import pytest


@pytest.fixture(scope="function")
def fix_syspath(tmp_path):
    """
    This is the current solution to the empty string being missing
    from sys.path when running pytest."""
    old_path = sys.path
    old_modules = dict(sys.modules)
    sys.path.insert(0, "")
    os.chdir(tmp_path)
    yield tmp_path
    for module in list(sys.modules):
        if module not in old_modules:
            del sys.modules[module]
    sys.path = old_path
