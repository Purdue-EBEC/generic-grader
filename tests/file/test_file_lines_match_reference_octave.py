"""End-to-end tests wiring the Octave runtime into
``file_lines_match_reference``.

The mechanics here are language-agnostic: the ``@reference_test``
decorator renames the file the student's code produced to ``sub_``
prefix and the reference-produced file to ``ref_`` prefix, then the
test opens both and compares them.  The point of these tests is to
prove that the Octave runtime creates files in the same working
directory the decorator expects.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from generic_grader.file.file_lines_match_reference import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


# A tiny Octave script that writes two known lines to ``out.txt``.
# Kept as a module-level constant so the "matching" and "mismatching"
# tests can share the reference body while varying only the sub body.
_REF_WRITER = textwrap.dedent(
    """\
    fid = fopen('out.txt', 'w');
    fprintf(fid, 'alpha\\nbeta\\n');
    fclose(fid);
    """
)


def test_matching_file_content_passes(fix_syspath, write_octave_pair, run_built_test):
    """Identical writer scripts \u2192 identical files \u2192 test passes."""
    write_octave_pair(fix_syspath, sub=_REF_WRITER, ref=_REF_WRITER, name="writer")
    options = Options(
        language="octave",
        obj_name="writer",
        sub_module="writer",
        ref_module="ref_writer",
        filenames=("out.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_mismatched_file_content_fails(fix_syspath, write_octave_pair, run_built_test):
    """When the student writes a different line, the diff-based
    comparison must surface a failure."""
    sub_body = textwrap.dedent(
        """\
        fid = fopen('out.txt', 'w');
        fprintf(fid, 'alpha\\nGAMMA\\n');
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=sub_body, ref=_REF_WRITER, name="writer")
    options = Options(
        language="octave",
        obj_name="writer",
        sub_module="writer",
        ref_module="ref_writer",
        filenames=("out.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()


def test_multiple_files_pass(fix_syspath, write_octave_pair, run_built_test):
    """The test type supports checking multiple files in one run \u2014
    make sure that works when the writer is Octave."""
    body = textwrap.dedent(
        """\
        fid = fopen('a.txt', 'w'); fprintf(fid, 'A\\n'); fclose(fid);
        fid = fopen('b.txt', 'w'); fprintf(fid, 'B\\n'); fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=body, ref=body, name="pair")
    options = Options(
        language="octave",
        obj_name="pair",
        sub_module="pair",
        ref_module="ref_pair",
        filenames=("a.txt", "b.txt"),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures
