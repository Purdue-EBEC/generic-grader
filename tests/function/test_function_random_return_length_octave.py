"""End-to-end tests wiring the Octave runtime into
``function_random_return_length``.

The test type calls the student's function repeatedly and takes
``len(returned_value)`` on each call.  In Python that works for any
sized iterable; in Octave the natural equivalent is a row vector
whose length depends on the input.  The runtime encodes each vector
as a JSON array which we decode back into a :class:`numpy.ndarray`
\u2014 and ``len(np.array(...))`` returns the first-axis size, so
the existing test logic works unchanged.

We also assert that scalars (returned by an Octave function with no
sized output) trigger the type-error branch that fails with the
\"did not return a value that has a length\" hint \u2014 so students
who forget to build the vector still get a friendly error instead of
an opaque traceback.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil

import pytest

from generic_grader.function.function_random_return_length import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def _write(tmp, name, body):
    (tmp / f"{name}.m").write_text(body)


def test_matching_lengths_pass(fix_syspath, run_built_test):
    """A function that always returns a length-3 vector satisfies
    ``expected_set = {3}``."""
    _write(
        fix_syspath,
        "triple",
        "function v = triple(~)\n" "  v = [1, 2, 3];\n" "endfunction\n",
    )
    options = Options(
        language="octave",
        obj_name="triple",
        sub_module="triple",
        ref_module="triple",
        # `args=()` would trigger script mode; supplying a placeholder
        # kwarg pushes us into function mode where the sidecar fires.
        # ``triple`` ignores it, which is legal Octave.
        args=(0,),
        expected_set={3},
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), (result.failures, result.errors)


def test_wrong_length_fails(fix_syspath, run_built_test, combined_error_text):
    """A function returning the wrong length triggers the standard
    \"did not match the expected lengths\" failure text."""
    _write(
        fix_syspath,
        "four_of_them",
        "function v = four_of_them(~)\n" "  v = [1, 2, 3, 4];\n" "endfunction\n",
    )
    options = Options(
        language="octave",
        obj_name="four_of_them",
        sub_module="four_of_them",
        ref_module="four_of_them",
        args=(0,),
        expected_set={3},  # expecting 3, function returns 4
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    # Message wraps at column limit, so match tolerantly.
    assert "did not match" in text
    assert "expected" in text and "lengths" in text


def test_scalar_return_fails_with_length_hint(
    fix_syspath, run_built_test, combined_error_text
):
    """When the callable returns a bare scalar it has no ``len()`` in
    Python; the test surfaces the \"did not return a value that has
    a length\" hint rather than a raw ``TypeError``."""
    _write(
        fix_syspath,
        "just_a_number",
        "function y = just_a_number(~)\n" "  y = 7;\n" "endfunction\n",
    )
    options = Options(
        language="octave",
        obj_name="just_a_number",
        sub_module="just_a_number",
        ref_module="just_a_number",
        args=(0,),
        expected_set={1},
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    # Same word-wrap concern; the key phrase is "has a length".
    assert "did not return a value" in text
    assert "has a length" in text
