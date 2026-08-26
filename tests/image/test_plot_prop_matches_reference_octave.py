"""End-to-end tests wiring the Octave runtime into
``plot_prop_matches_reference``.

Each test pairs a student ``.m`` script and a reference ``.m`` script,
runs the built ``TestCase`` in-process, and checks that the pass/fail
outcome and hint text match what the Python plot tests do for
equivalent matplotlib code.  The Octave runtime captures a JSON
sidecar of plot properties after each run
(:func:`generic_grader.runtimes.octave._build_plot_capture_snippet`);
:mod:`generic_grader.utils.octave_plot` decodes it into the same
Python types the matplotlib path returns, and
:mod:`generic_grader.image.plot_prop_matches_reference` compares
them with the same message shape used for Python plot tests.

Skipped automatically on hosts without GNU Octave on ``PATH``.
"""

from __future__ import annotations

import shutil

import pytest

from generic_grader.image.plot_prop_matches_reference import build
from generic_grader.runtimes.octave import OCTAVE_EXECUTABLE
from generic_grader.utils.options import Options

pytestmark = pytest.mark.skipif(
    shutil.which(OCTAVE_EXECUTABLE) is None, reason="GNU Octave not installed"
)


# ---------------------------------------------------------------------------
# Reusable Octave plot scripts.  Each script sets a title / labels / limits /
# data explicitly so tests can pin down exactly what property the harness
# should observe.  ``main`` is used as the obj_name for parity with the
# equivalent Python plot tests.
# ---------------------------------------------------------------------------
PLOT_ONE = (
    "plot([1, 2, 3, 4], [1, 4, 9, 16]);\n"
    "title('Simple plot');\n"
    "xlabel('x-axis');\n"
    "ylabel('y-axis');\n"
)

PLOT_TWO = (
    "plot([1, 2, 3, 4, 5], [1, 4, 9, 16, 25]);\n"
    "title('Simple plot 2');\n"
    "xlabel('fake line on bottom');\n"
    "ylabel('y-axis-2');\n"
)

# Two-line reference used only when the mismatch under test is the line
# count itself — keeping the other passing/failing cases on the
# single-line PLOT_ONE / PLOT_TWO pair keeps failure messages uncluttered.
PLOT_TWO_LINES = (
    "plot([1, 2, 3, 4], [1, 4, 9, 16]);\n"
    "hold on;\n"
    "plot([1, 2, 3, 4], [2, 5, 10, 17]);\n"
    "title('Simple plot');\n"
)


def _octave_options(prop, **overrides):
    """Build an ``Options`` instance for the Octave plot test.

    Keeping the boilerplate in one helper means each parameterised
    case only names the ``prop`` (and any ``ratio`` override for
    fuzzy string comparisons) — the language, module names, and
    weight are identical across every test.
    """
    kwargs = dict(
        language="octave",
        prop=prop,
        weight=1,
        ref_module="ref_main",
        sub_module="main",
    )
    kwargs.update(overrides)
    return Options(**kwargs)


# ---------------------------------------------------------------------------
# Passing cases
# ---------------------------------------------------------------------------
PASSING_CASES = [
    ("title", PLOT_ONE, PLOT_ONE),
    ("x label", PLOT_ONE, PLOT_ONE),
    ("y label", PLOT_ONE, PLOT_ONE),
    ("x limits", PLOT_ONE, PLOT_ONE),
    ("y limits", PLOT_ONE, PLOT_ONE),
    ("x tick labels", PLOT_ONE, PLOT_ONE),
    ("y tick labels", PLOT_ONE, PLOT_ONE),
    ("number of lines", PLOT_ONE, PLOT_ONE),
    ("x data", PLOT_ONE, PLOT_ONE),
    ("y data", PLOT_ONE, PLOT_ONE),
    ("xy data", PLOT_ONE, PLOT_ONE),
]


@pytest.mark.parametrize("prop, sub_text, ref_text", PASSING_CASES)
def test_matching_property_passes(
    fix_syspath, write_octave_pair, run_built_test, prop, sub_text, ref_text
):
    """Reference and student produce identical plots — every supported
    property compares equal and the test passes."""
    write_octave_pair(fix_syspath, sub=sub_text, ref=ref_text, name="main")
    result = run_built_test(_octave_options(prop), build)
    assert result.wasSuccessful(), (result.failures, result.errors)


# ---------------------------------------------------------------------------
# Failing cases — pair PLOT_ONE against PLOT_TWO and confirm the "did not
# match" hint is present.  ``xy data`` uses an RMS-error threshold, so we
# hand it obviously-different x/y ranges.
# ---------------------------------------------------------------------------
FAILING_CASES = [
    ("title", 1.0),
    ("x label", 0.5),  # string prop with fuzzy ratio still fails on very
    ("y label", 1.0),  # different labels
    ("x limits", 1.0),
    ("y limits", 1.0),
    ("x tick labels", 1.0),
    ("y tick labels", 1.0),
    ("x data", 1.0),
    ("y data", 1.0),
    ("xy data", 1.0),
]


def test_mismatched_number_of_lines_fails(
    fix_syspath, write_octave_pair, run_built_test, combined_error_text
):
    """A single-line student plot versus a two-line reference triggers
    the ``number of lines`` mismatch — exercised separately from the
    other single-line failing cases so the reference source stays
    consistent across the rest of the parameterised failures."""
    write_octave_pair(fix_syspath, sub=PLOT_ONE, ref=PLOT_TWO_LINES, name="main")
    result = run_built_test(_octave_options("number of lines"), build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    assert "did not match" in text


@pytest.mark.parametrize("prop, ratio", FAILING_CASES)
def test_mismatched_property_fails(
    fix_syspath,
    write_octave_pair,
    run_built_test,
    combined_error_text,
    prop,
    ratio,
):
    """When the student's plot differs from the reference, the test
    fails with the standard "did not match the expected plot" hint —
    exactly the same message shape the Python path produces."""
    write_octave_pair(fix_syspath, sub=PLOT_ONE, ref=PLOT_TWO, name="main")
    result = run_built_test(_octave_options(prop, ratio=ratio), build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    assert "did not match" in text
    assert "expected plot" in text


def test_line_colors_match(fix_syspath, write_octave_pair, run_built_test):
    """Line colours are decoded from RGB triples into named colours,
    matching :func:`generic_grader.utils.plot.get_line_colors` — so a
    reference plot with a red line compares equal to a student plot
    with the same red line."""
    body = "plot([1, 2, 3, 4], [1, 4, 9, 16], 'r');\n" "title('Simple plot');\n"
    write_octave_pair(fix_syspath, sub=body, ref=body, name="main")
    result = run_built_test(_octave_options("line colors"), build)
    assert result.wasSuccessful(), (result.failures, result.errors)


def test_missing_plot_fails_with_hint(
    fix_syspath, write_octave_pair, run_built_test, combined_error_text
):
    """Student code that never calls ``plot`` produces no figure —
    :func:`utils.octave_plot._primary_axes` fails the test with the
    same "make sure your code produces a plot of some type" text the
    Python path uses when :func:`plot.get_current_axes` finds nothing.
    """
    write_octave_pair(
        fix_syspath,
        sub="disp('no plot here');\n",  # no figure created
        ref=PLOT_ONE,
        name="main",
    )
    result = run_built_test(_octave_options("title"), build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    assert "produces a plot" in text


def test_x_data_index_out_of_range(
    fix_syspath, write_octave_pair, run_built_test, combined_error_text
):
    """Asking for x data of a line that doesn't exist raises the same
    "Failed to find x data for data set N" message the Python side
    raises via ``IndexError`` in :func:`plot.get_x_data`."""
    write_octave_pair(fix_syspath, sub=PLOT_ONE, ref=PLOT_ONE, name="main")
    result = run_built_test(_octave_options("x data", prop_kwargs={"index": 5}), build)
    assert not result.wasSuccessful()
    text = combined_error_text(result)
    assert "Failed to find x data for data set 6" in text
