"""End-to-end tests wiring the Octave runtime into
``file_lines_are_random``.

This test type runs the student's submission twice via two separate
``SubUser`` instances and asserts the produced files differ.  For
Octave this exercises the runtime's stateless-subprocess guarantee:
two invocations must not share PRNG state (or anything else) that
would make a genuinely-random script produce the same file twice.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

from generic_grader.file.file_lines_are_random import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_random_file_content_passes(fix_syspath, write_octave_pair, run_built_test):
    """Two subprocess invocations of a ``randi``-based writer produce
    different files with vanishing collision probability
    (1/1_000_000 per pair)."""
    body = textwrap.dedent(
        """\
        fid = fopen('r.txt', 'w');
        fprintf(fid, '%d\\n', randi(1000000));
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=body, ref=body, name="rrand")
    options = Options(
        language="octave",
        obj_name="rrand",
        sub_module="rrand",
        ref_module="ref_rrand",
        filenames=("r.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_constant_file_content_fails(fix_syspath, write_octave_pair, run_built_test):
    """A writer that always emits the same byte sequence must fail
    the randomness check."""
    body = textwrap.dedent(
        """\
        fid = fopen('r.txt', 'w');
        fprintf(fid, '%d\\n', 7);
        fclose(fid);
        """
    )
    write_octave_pair(fix_syspath, sub=body, ref=body, name="crand")
    options = Options(
        language="octave",
        obj_name="crand",
        sub_module="crand",
        ref_module="ref_crand",
        filenames=("r.txt",),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    _, err_msg = result.failures[0]
    # Anchor the assertion on a stable fragment of the hint.
    assert "not appear to be random" in err_msg
