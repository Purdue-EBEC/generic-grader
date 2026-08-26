"""End-to-end tests wiring the Octave runtime into
``file_is_identical``.

``file_is_identical`` does a byte-for-byte comparison between the
student-produced file (``sub_<name>``) and the reference-produced
file (``ref_<name>``).  Because that comparison is at the byte level
it's a stricter test than ``file_lines_match_reference`` \u2014
trailing whitespace, differing line endings, and encoding
differences all matter.  These integration tests confirm the Octave
runtime lands bytes on disk in a compatible way.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from generic_grader.file.file_is_identical import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_identical_bytes_pass(fix_syspath, write_octave_pair, run_built_test):
    """Two identical writers land identical bytes on disk \u2014 the
    byte comparison succeeds."""
    body = textwrap.dedent(
        """\
        fid = fopen('ident.txt', 'w');
        fprintf(fid, 'hello world');
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=body, ref=body, name="identer")
    options = Options(
        language="octave",
        obj_name="identer",
        sub_module="identer",
        ref_module="ref_identer",
        filenames=("ident.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_trailing_whitespace_diff_fails(fix_syspath, write_octave_pair, run_built_test):
    """A student who adds a stray trailing space fails the byte
    comparison even though the file *content* looks the same."""
    sub_body = textwrap.dedent(
        """\
        fid = fopen('ident.txt', 'w');
        fprintf(fid, 'hello world ');
        fclose(fid);
        """
    )
    ref_body = textwrap.dedent(
        """\
        fid = fopen('ident.txt', 'w');
        fprintf(fid, 'hello world');
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=sub_body, ref=ref_body, name="identer")
    options = Options(
        language="octave",
        obj_name="identer",
        sub_module="identer",
        ref_module="ref_identer",
        filenames=("ident.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
