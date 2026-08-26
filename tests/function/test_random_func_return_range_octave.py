"""End-to-end tests wiring the Octave runtime into
``random_func_return_range``.

The test type calls the student's function up to ``n_trials(N)`` times
and collects the set of returned scalars, checking that it exactly
matches ``expected_set``.  In the Octave path, each scalar comes back
as a Python ``float`` after the JSON round-trip \u2014 so
``expected_set`` values are floats too.

We keep the ``expected_set`` small (two or three values) to keep the
integration test fast: ``n_trials(2)`` is ~207 calls, ``n_trials(3)``
is ~575, and each call is a fresh Octave subprocess (~50\u2013100 ms
warm).  Running the full suite therefore adds a few seconds on hosts
with Octave installed \u2014 acceptable, and much cheaper than a
100+-element range would be.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil

import pytest

from generic_grader.function.random_func_return_range import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


def _write(tmp, name, body):
    (tmp / f"{name}.m").write_text(body)


def test_matching_range_passes(fix_syspath, run_built_test):
    """A function that uniformly returns 1 or 2 matches
    ``expected_set = {1.0, 2.0}`` \u2014 the collection loop stops
    early as soon as it has both values."""
    _write(
        fix_syspath,
        "coin",
        # `randi(2)` returns 1 or 2 uniformly.  We keep the domain
        # tiny so ``n_trials(2)`` is only ~207 subprocesses.
        "function y = coin(~)\n" "  y = randi(2);\n" "endfunction\n",
    )
    options = Options(
        language="octave",
        obj_name="coin",
        sub_module="coin",
        ref_module="coin",
        args=(0,),
        expected_set={1.0, 2.0},
        weight=1,
    )
    result = run_built_test(options, build)
    assert result.wasSuccessful(), (result.failures, result.errors)


def test_missing_value_fails(fix_syspath, run_built_test, combined_error_text):
    """A function that never returns 2 (always 1) fails the equality
    check with the standard \"did not match the expected range\"
    text."""
    _write(
        fix_syspath,
        "always_one",
        "function y = always_one(~)\n" "  y = 1;\n" "endfunction\n",
    )
    options = Options(
        language="octave",
        obj_name="always_one",
        sub_module="always_one",
        ref_module="always_one",
        args=(0,),
        expected_set={1.0, 2.0},  # never sees 2
        weight=1,
    )
    result = run_built_test(options, build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    # Message wraps at column limit; assert tolerantly.
    assert "did not match" in text
    assert "range" in text
