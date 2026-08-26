"""Root pytest configuration and shared fixtures."""

import os
import shutil
import sys
import unittest
from pathlib import Path

import pytest

from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE

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


# ---------------------------------------------------------------------------
# Octave end-to-end test helpers
#
# The Octave integration tests share a small amount of boilerplate for
# writing paired student / reference ``.m`` files and running a built
# ``unittest.TestCase`` in-process.  Exposing that boilerplate through
# fixtures (rather than a plain helpers module) sidesteps the fact that
# ``tests/`` intentionally is *not* a package \u2014 several tests in
# ``tests/utils/test_importer.py`` create fresh files under a temp
# ``tests/`` directory and import them, which would break if a real
# ``tests/__init__.py`` existed.  Fixtures are always resolvable through
# pytest's rootdir-aware discovery, so they work regardless of package
# layout.
# ---------------------------------------------------------------------------


# Detect Octave once at import time so the skip marker used by the
# Octave integration test modules is consistent across the whole
# suite.  Honour the ``OCTAVE_EXECUTABLE`` env override captured at
# ``generic_grader.runtimes.octave`` import time so this check matches
# the one the runtime will do at execution time.
_HAVE_OCTAVE = shutil.which(OCTAVE_EXECUTABLE) is not None


#: A ready-to-use ``pytest.mark.skipif`` that Octave integration test
#: modules apply at module scope via ``pytestmark = requires_octave``.
requires_octave = pytest.mark.skipif(
    not _HAVE_OCTAVE, reason="GNU Octave not installed"
)


@pytest.fixture
def write_octave_pair():
    """Return a helper that writes a matched student / reference
    ``.m`` file pair.

    Usage::

        def test_thing(fix_syspath, write_octave_pair):
            write_octave_pair(fix_syspath, sub=..., ref=..., name="foo")

    The reference file is stored with the ``ref_`` prefix so it can
    coexist with the student's file in the same working directory,
    matching the convention the ``reference_test`` decorator uses
    when it swaps ``sub_module`` for ``ref_module`` between the
    reference and submitted runs.
    """

    def _write(tmp: Path, *, sub: str, ref: str, name: str, ref_prefix: str = "ref_"):
        (tmp / f"{name}.m").write_text(sub)
        (tmp / f"{ref_prefix}{name}.m").write_text(ref)

    return _write


@pytest.fixture
def run_built_test():
    """Return a helper that assembles and executes the unittest class
    produced by a ``build`` function, returning the ``TestResult``.

    The runner's output stream is silenced so tests can inspect the
    ``TestResult`` object directly without dumping unittest chatter
    to the console.
    """

    def _run(options, build):
        cls = build(options)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        with open(os.devnull, "w") as devnull:
            runner = unittest.TextTestRunner(verbosity=0, stream=devnull)
            return runner.run(suite)

    return _run


@pytest.fixture
def combined_error_text():
    """Return a helper that concatenates ``(name, msg)`` text from
    both ``result.failures`` and ``result.errors``.

    Useful when a test asserts on the *content* of the failure message
    and doesn't care whether the exception was the ``TestCase``'s
    default ``failureException`` (routed to ``.failures``) or a
    different exception (routed to ``.errors``).
    """

    def _text(result):
        return "\n".join(msg for _, msg in result.failures + result.errors)

    return _text
