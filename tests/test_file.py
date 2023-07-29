import unittest

import pytest
from parameterized import param

from generic_grader.file.file_presence import build
from generic_grader.utils.options import Options


@pytest.fixture()
def built_class():
    """Provide the class built by the build function."""
    o = Options()
    params = param(o)
    return build(params)


def test_file_presence_build_class(built_class):
    """Test that the file presence build function returns a class."""
    assert issubclass(built_class, unittest.TestCase)


def test_file_presence_build_instance(built_class):
    """Test that the built_class returns an instance of unittest.TestCase."""
    assert isinstance(built_class(), unittest.TestCase)
