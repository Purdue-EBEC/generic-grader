"""Unit tests for :mod:`generic_grader.utils.language_guard`.

These cover the helper itself; the per-test-type guards are exercised
in the module-level tests under ``tests/style``, ``tests/class_``,
``tests/function``, ``tests/file``, and ``tests/image``.
"""

from __future__ import annotations

import unittest

import pytest

from generic_grader.utils.language_guard import require_python_language
from generic_grader.utils.options import Options


class DummyTest(unittest.TestCase):
    def runTest(self):  # pragma: no cover
        pass


@pytest.fixture()
def test_case():
    return DummyTest()


def test_python_language_is_no_op(test_case):
    # Default Options.language == "python" -> the guard must return
    # without raising.
    require_python_language(test_case, Options(), "some.test_type")


def test_octave_language_fails_with_test_type_and_language(test_case):
    with pytest.raises(AssertionError) as exc:
        require_python_language(test_case, Options(language="octave"), "style.comments")
    message = str(exc.value)
    assert "Python-only" in message
    assert "style.comments" in message
    assert "'octave'" in message


def test_missing_language_attribute_is_treated_as_python(test_case):
    # A bare ``SimpleNamespace``-style options object without the
    # ``language`` attribute should behave like ``language="python"``
    # so tests written before the field existed keep working.
    class LegacyOptions:
        pass

    require_python_language(test_case, LegacyOptions(), "class_.class_is_defined")


def test_none_language_is_treated_as_python(test_case):
    class NoneOptions:
        language = None

    require_python_language(test_case, NoneOptions(), "function.static_loop_depth")
