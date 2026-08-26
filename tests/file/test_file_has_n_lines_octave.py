"""End-to-end tests wiring the Octave runtime into
``file_has_n_lines``.

The check compares ``len(sub.splitlines()) == len(ref.splitlines())``
for each configured filename, so as long as the Octave subprocess
lands its output in the working directory with newline conventions
matching the reference (which it does \u2014 both go through Octave's
same ``fprintf``), the test just works.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from generic_grader.file.file_has_n_lines import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_matching_line_count_passes(fix_syspath, write_octave_pair, run_built_test):
    """Both writers emit three lines \u2014 the test passes."""
    body = textwrap.dedent(
        """\
        fid = fopen('three.txt', 'w');
        fprintf(fid, 'a\\nb\\nc\\n');
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=body, ref=body, name="threer")
    options = Options(
        language="octave",
        obj_name="threer",
        sub_module="threer",
        ref_module="ref_threer",
        filenames=("three.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_wrong_line_count_fails(fix_syspath, write_octave_pair, run_built_test):
    """Reference writes three lines, student writes two \u2014 the
    length comparison fails."""
    sub_body = textwrap.dedent(
        """\
        fid = fopen('three.txt', 'w');
        fprintf(fid, 'a\\nb\\n');
        fclose(fid);
        """
    )
    ref_body = textwrap.dedent(
        """\
        fid = fopen('three.txt', 'w');
        fprintf(fid, 'a\\nb\\nc\\n');
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=sub_body, ref=ref_body, name="threer")
    options = Options(
        language="octave",
        obj_name="threer",
        sub_module="threer",
        ref_module="ref_threer",
        filenames=("three.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
