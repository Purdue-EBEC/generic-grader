import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup():
    sys.path.append("")
    yield
    sys.path.remove("")
