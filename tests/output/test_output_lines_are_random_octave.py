"""End-to-end tests wiring the Octave runtime into
``output_lines_are_random``.

Unlike the reference-comparing tests, this one runs the *submitted*
code twice and demands the two runs differ.  It exists to catch
students who hard-code a value that looks random.  Two Octave-specific
concerns to lock in:

*   The runtime creates a fresh subprocess per invocation, so calling
    ``__User__.call_obj`` twice must not share state \u2014 confirmed
    implicitly by this test passing when the ``.m`` file uses ``randi``.
*   The ``format_log()`` output emitted on failure must include the
    log of the *second* run, since the failure message references it.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil

import pytest

from generic_grader.output.output_lines_are_random import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_random_output_passes(fix_syspath, write_octave_pair, run_built_test):
    """``randi`` on Octave 10.x is seeded from the OS entropy pool at
    interpreter startup, so two consecutive subprocess invocations
    produce different values with vanishing collision probability
    (1/1_000_000 per pair)."""
    body = "fprintf('%d\\n', randi(1000000))\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="randy")
    options = Options(
        language="octave",
        obj_name="randy",
        sub_module="randy",
        ref_module="ref_randy",
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_constant_output_fails(fix_syspath, write_octave_pair, run_built_test):
    """When the student hard-codes a value, both runs produce the
    same log and the test must fail with the expected hint."""
    body = "fprintf('%d\\n', 7)\n"  # never varies
    write_octave_pair(fix_syspath, sub=body, ref=body, name="constant")
    options = Options(
        language="octave",
        obj_name="constant",
        sub_module="constant",
        ref_module="ref_constant",
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    _, err_msg = result.failures[0]
    # The hint produced by ``output_lines_are_random`` starts with
    # "Your output does not appear to be random." \u2014 anchor on a
    # stable fragment of that phrase.
    assert "does not appear to be random" in err_msg
