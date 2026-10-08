"""End-to-end tests wiring the Octave runtime into
``output_lines_match_reference``.

These tests deliberately duplicate a small slice of the Python
end-to-end coverage in :mod:`test_output_lines_match_reference`, but
with ``language="octave"`` \u2014 the point is to catch any *seam*
regression between :class:`OctaveRuntime`,
:class:`~generic_grader.utils.user.__User__`, and the existing
``reference_test`` decorator.

Skipped automatically on hosts without GNU Octave on ``PATH`` so
contributors don't need it installed just to run the pytest suite.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from generic_grader.output.output_lines_match_reference import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_matching_script_outputs_pass(fix_syspath, write_octave_pair, run_built_test):
    """The happy path: two script-mode files print the same text and
    the test passes."""
    write_octave_pair(
        fix_syspath,
        sub="disp('hello world')\n",
        ref="disp('hello world')\n",
        name="hello",
    )
    options = Options(
        language="octave",
        obj_name="hello",
        sub_module="hello",
        ref_module="ref_hello",
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful()
    assert result.testsRun == 1


def test_mismatched_outputs_fail_with_hint(
    fix_syspath, write_octave_pair, run_built_test
):
    """When the student's Octave output differs from the reference,
    the test must fail with the standard \"did not match\" hint \u2014
    the same message the Python path produces."""
    write_octave_pair(
        fix_syspath,
        sub="disp('goodbye world')\n",
        ref="disp('hello world')\n",
        name="hello",
    )
    options = Options(
        language="octave",
        obj_name="hello",
        sub_module="hello",
        ref_module="ref_hello",
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    assert result.testsRun == 1
    _, err_msg = result.failures[0]
    assert "did not match" in err_msg
    assert "hello" in err_msg  # obj_name surfaces in the message


def test_function_mode_with_argument(fix_syspath, write_octave_pair, run_built_test):
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
    write_octave_pair(fix_syspath, sub=body, ref=body, name="double_it")
    options = Options(
        language="octave",
        obj_name="double_it",
        sub_module="double_it",
        ref_module="ref_double_it",
        args=(21,),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_missing_student_file_fails_with_filenotfound(
    fix_syspath, run_built_test, combined_error_text
):
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
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    # ``FileNotFoundError`` is the failureException we install in
    # ``OctaveRuntime.resolve`` when the .m file is missing.  It
    # comes out on ``.errors`` (not ``.failures``) because it is
    # not the ``TestCase.failureException`` default.
    assert "Unable to load `hello.m`" in combined_error_text(result)
