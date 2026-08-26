"""End-to-end tests wiring the Octave runtime into
``output_lines_match_reference``.

These tests deliberately duplicate a small slice of the Python
end-to-end coverage in :mod:`test_output_lines_match_reference`, but
with ``language=\"octave\"`` \u2014 the point is to catch any *seam*
regression between :class:`OctaveRuntime`,
:class:`~generic_grader.utils.user.__User__`, and the existing
``reference_test`` decorator.

Skipped automatically on hosts without GNU Octave on ``PATH`` so
contributors don't need it installed just to run the pytest suite.
"""

from __future__ import annotations

import shutil
import textwrap
import unittest

import pytest

from generic_grader.output.output_lines_match_reference import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

_HAVE_OCTAVE = shutil.which(OCTAVE_EXECUTABLE) is not None
pytestmark = pytest.mark.skipif(not _HAVE_OCTAVE, reason="GNU Octave not installed")


def _write_pair(fix_syspath, sub_body, ref_body, name="hello", ref_prefix="ref_"):
    """Write a matched student/reference pair of ``.m`` files."""
    (fix_syspath / f"{name}.m").write_text(sub_body)
    (fix_syspath / f"{ref_prefix}{name}.m").write_text(ref_body)


def _run(options):
    """Execute the built test class and return the ``TestResult``."""
    cls = build(options)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(cls)
    runner = unittest.TextTestRunner(verbosity=0, stream=open("/dev/null", "w"))
    return runner.run(suite)


def test_matching_script_outputs_pass(fix_syspath):
    """The happy path: two script-mode files print the same text and
    the test passes."""
    _write_pair(
        fix_syspath,
        sub_body="disp('hello world')\n",
        ref_body="disp('hello world')\n",
    )
    options = Options(
        language="octave",
        obj_name="hello",
        sub_module="hello",
        ref_module="ref_hello",
        weight=1,
    )
    result = _run(options)
    assert result.wasSuccessful()
    assert result.testsRun == 1


def test_mismatched_outputs_fail_with_hint(fix_syspath):
    """When the student's Octave output differs from the reference,
    the test must fail with the standard \"did not match\" hint \u2014
    the same message the Python path produces."""
    _write_pair(
        fix_syspath,
        sub_body="disp('goodbye world')\n",
        ref_body="disp('hello world')\n",
    )
    options = Options(
        language="octave",
        obj_name="hello",
        sub_module="hello",
        ref_module="ref_hello",
        weight=1,
    )
    result = _run(options)
    assert not result.wasSuccessful()
    assert result.testsRun == 1
    _, err_msg = result.failures[0]
    assert "did not match" in err_msg
    assert "hello" in err_msg  # obj_name surfaces in the message


def test_function_mode_with_argument(fix_syspath):
    """Function-mode dispatch: the presence of ``args`` (non-empty)
    routes through ``<obj_name>(<args>)`` in both the ref and sub
    Octave runs."""
    body = textwrap.dedent(
        """\
        function double_it(n)
          fprintf('%d\\n', 2 * n);
        end
        """
    )
    _write_pair(fix_syspath, sub_body=body, ref_body=body, name="double_it")
    options = Options(
        language="octave",
        obj_name="double_it",
        sub_module="double_it",
        ref_module="ref_double_it",
        args=(21,),
        weight=1,
    )
    result = _run(options)
    assert result.wasSuccessful(), result.failures


def test_missing_student_file_fails_with_filenotfound(fix_syspath):
    """The reference file exists but the student never submitted \u2014
    the test must fail with the runtime's \"Unable to load\" message,
    not a generic assertion error."""
    (fix_syspath / "ref_hello.m").write_text("disp('hello world')\n")
    options = Options(
        language="octave",
        obj_name="hello",
        sub_module="hello",
        ref_module="ref_hello",
        weight=1,
    )
    result = _run(options)
    assert not result.wasSuccessful()
    # ``FileNotFoundError`` is the failureException we install in
    # ``OctaveRuntime.resolve`` when the .m file is missing.  It
    # comes out on ``.errors`` (not ``.failures``) because it is
    # not the ``TestCase.failureException`` default.
    text = "\n".join(msg for _, msg in result.failures + result.errors)
    assert "Unable to load `hello.m`" in text
