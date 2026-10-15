"""End-to-end tests wiring the Octave runtime into
``function_return_values_match_reference``.

Unlike the log-based tests, this one *does* care about the return
value(s) the runtime captured.  These tests exercise:

* The Octave runtime's ``jsonencode`` sidecar + Python-side decode
  round-trip against real Octave.
* The scalar / vector / multi-return branches of
  ``function_return_values_match_reference.build`` \u2014 confirming
  the ``np.ndarray`` branch fires for vectors decoded from JSON and
  the ``safe_assert_equal`` branch fires for scalars.
* The ``@reference_test`` decorator's swap between the reference
  (``ref_<name>.m``) and student (``<name>.m``) invocations, which is
  runtime-agnostic but must still route each call to Octave.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil

import pytest

from generic_grader.function.function_return_values_match_reference import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def test_matching_scalar_return_passes(fix_syspath, write_octave_pair, run_built_test):
    """Both sides return the same scalar \u2014 the safe-equal branch
    (via ``assertAlmostEqual`` for floats) passes cleanly."""
    body = "function y = double_it(x)\n" "  y = x * 2;\n" "endfunction\n"
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
    assert result.wasSuccessful(), (result.failures, result.errors)


def test_mismatched_scalar_fails_with_hint(
    fix_syspath, write_octave_pair, run_built_test, combined_error_text
):
    """The student returns a different scalar \u2014 the test fails with
    the standard \"did not match the expected return value(s)\" hint."""
    write_octave_pair(
        fix_syspath,
        sub="function y = double_it(x)\n  y = x * 3;\nendfunction\n",  # wrong: * 3
        ref="function y = double_it(x)\n  y = x * 2;\nendfunction\n",
        name="double_it",
    )
    options = Options(
        language="octave",
        obj_name="double_it",
        sub_module="double_it",
        ref_module="ref_double_it",
        args=(21,),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    # The hint wraps at the column limit, so match tolerantly —
    # "did not match" and "expected return value(s)" both survive
    # any reasonable line wrap.
    assert "did not match" in text
    assert "return value(s)" in text


def test_matching_vector_return_passes(fix_syspath, write_octave_pair, run_built_test):
    """Row vectors round-trip as ``np.ndarray`` on both sides, so the
    ``array_compare`` branch fires and passes when they're identical."""
    body = "function v = range_of(n)\n" "  v = 1:n;\n" "endfunction\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="range_of")
    options = Options(
        language="octave",
        obj_name="range_of",
        sub_module="range_of",
        ref_module="ref_range_of",
        args=(5,),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), (result.failures, result.errors)


def test_mismatched_vector_fails(
    fix_syspath, write_octave_pair, run_built_test, combined_error_text
):
    """Vectors of the same length but different values trigger the
    ``array_compare`` unequal-values path."""
    write_octave_pair(
        fix_syspath,
        sub="function v = range_of(n)\n  v = (1:n) + 1;\nendfunction\n",  # off by 1
        ref="function v = range_of(n)\n  v = 1:n;\nendfunction\n",
        name="range_of",
    )
    options = Options(
        language="octave",
        obj_name="range_of",
        sub_module="range_of",
        ref_module="ref_range_of",
        args=(4,),
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    assert "did not match" in text
    assert "return value(s)" in text


def test_matching_multiple_return_values_pass(
    fix_syspath, write_octave_pair, run_built_test
):
    """``[a, b] = f(x)`` on both sides yields a tuple on each side;
    equal tuples pass through the ``safe_assert_equal`` path."""
    body = "function [a, b] = pair(x)\n" "  a = x;\n" "  b = x + 1;\n" "endfunction\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="pair")
    options = Options(
        language="octave",
        obj_name="pair",
        sub_module="pair",
        ref_module="ref_pair",
        args=(9,),
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), (result.failures, result.errors)
