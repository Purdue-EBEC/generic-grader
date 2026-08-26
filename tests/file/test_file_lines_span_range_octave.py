"""End-to-end tests wiring the Octave runtime into
``file_lines_span_range``.

This test type checks that the *set* of lines the student writes
covers the same set of values the reference wrote \u2014 useful for
exercises that produce output in nondeterministic order but with
deterministic content.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from generic_grader.file.file_lines_span_range import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_matching_range_passes(fix_syspath, write_octave_pair, run_built_test):
    """Both writers produce the numbers 1..10 in order \u2014 the sets
    match and the test passes.  This shape mirrors the sample
    exercise in the docstring of the test type itself."""
    body = textwrap.dedent(
        """\
        fid = fopen('nums.txt', 'w');
        for k = 1:10
          fprintf(fid, '%d\\n', k);
        end
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=body, ref=body, name="ranger")
    options = Options(
        language="octave",
        obj_name="ranger",
        sub_module="ranger",
        ref_module="ref_ranger",
        filenames=("nums.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_missing_value_fails(fix_syspath, write_octave_pair, run_built_test):
    """Student writes 1..9 (missing 10) while the reference writes
    1..10 \u2014 the two sets differ and the assertion must fire."""
    sub_body = textwrap.dedent(
        """\
        fid = fopen('nums.txt', 'w');
        for k = 1:9
          fprintf(fid, '%d\\n', k);
        end
        fclose(fid);
        """
    )
    ref_body = textwrap.dedent(
        """\
        fid = fopen('nums.txt', 'w');
        for k = 1:10
          fprintf(fid, '%d\\n', k);
        end
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=sub_body, ref=ref_body, name="ranger")
    options = Options(
        language="octave",
        obj_name="ranger",
        sub_module="ranger",
        ref_module="ref_ranger",
        filenames=("nums.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
