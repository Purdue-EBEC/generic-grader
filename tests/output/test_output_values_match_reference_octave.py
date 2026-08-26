"""End-to-end tests wiring the Octave runtime into
``output_values_match_reference``.

This test type doesn't care about the *language* the code is written
in \u2014 it only inspects the I/O log the runtime tees during
execution.  The point of these tests is to prove that guarantee holds
for Octave: values printed via ``fprintf`` end up in the log in a
form that ``__User__.get_values()`` can extract with its existing
regex, and that the ``@reference_test`` decorator's swap between the
reference and student runs works identically to the Python path.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil

import pytest

from generic_grader.output.output_values_match_reference import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_matching_single_value_passes(fix_syspath, write_octave_pair, run_built_test):
    """The happy path: identical numeric output on both sides passes
    when we ask for ``value_n=1`` (the first number on the first line).
    """
    body = "fprintf('The answer is %d\\n', 42)\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="answer")
    options = Options(
        language="octave",
        obj_name="answer",
        sub_module="answer",
        ref_module="ref_answer",
        # ``line_n`` defaults to 1; ``value_n=1`` selects the first
        # number found on that line.
        value_n=1,
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_mismatched_value_fails_with_hint(
    fix_syspath, write_octave_pair, run_built_test
):
    """When the student's printed value differs from the reference,
    the test must fail with the standard \"output values did not
    match\" hint."""
    write_octave_pair(
        fix_syspath,
        sub="fprintf('The answer is %d\\n', 41)\n",
        ref="fprintf('The answer is %d\\n', 42)\n",
        name="answer",
    )
    options = Options(
        language="octave",
        obj_name="answer",
        sub_module="answer",
        ref_module="ref_answer",
        value_n=1,
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    assert result.testsRun == 1
    _, err_msg = result.failures[0]
    # ``output_values_match_reference`` builds a hint that includes
    # the phrase "output values did not match" \u2014 anchoring the
    # assertion on that string catches accidental message-format
    # regressions.
    assert "output values did not match" in err_msg


def test_multiple_values_on_one_line(fix_syspath, write_octave_pair, run_built_test):
    """The extractor should pull *all* numbers off the target line
    when ``value_n`` is omitted \u2014 verifying that Octave's default
    ``fprintf`` spacing is compatible with the number-matching regex.
    """
    body = "fprintf('x=%d y=%d z=%d\\n', 1, 2, 3)\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="triple")
    options = Options(
        language="octave",
        obj_name="triple",
        sub_module="triple",
        ref_module="ref_triple",
        # ``value_n`` left at default (``None``) triggers the
        # ``get_values()`` code path which returns every number on
        # the line.
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures


def test_floating_point_value_matches(fix_syspath, write_octave_pair, run_built_test):
    """Floats printed by Octave's default ``%f`` conversion should be
    extracted and compared like integers.  This also exercises the
    ``e[+-]d+`` branch of the regex indirectly (Octave defaults to
    fixed-point but any exponential form would also be caught)."""
    body = "fprintf('pi is %.4f\\n', pi)\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="pival")
    options = Options(
        language="octave",
        obj_name="pival",
        sub_module="pival",
        ref_module="ref_pival",
        value_n=1,
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), result.failures
