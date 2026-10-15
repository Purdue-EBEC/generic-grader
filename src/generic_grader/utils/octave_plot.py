"""Plot-property extraction for the Octave runtime.

The Python plot tests read live matplotlib global state via
:mod:`generic_grader.utils.plot`.  Octave has no equivalent global we
can inspect from Python, so the Octave runtime writes a JSON sidecar
after each student run (see
:func:`generic_grader.runtimes.octave._build_plot_capture_snippet`)
that captures the properties of every open figure.  This module
consumes that sidecar and returns the same Python-typed values the
:func:`generic_grader.utils.plot.get_property` dispatcher returns, so
:mod:`generic_grader.image.plot_prop_matches_reference` can compare
reference and student plots with a single language-dispatched
front-end and no other code changes.

The supported ``prop`` names are a subset of the Python dispatcher's:

* ``title``, ``x label``, ``y label``
* ``x limits``, ``y limits``
* ``x tick labels``, ``y tick labels``
* ``number of lines``, ``line colors``
* ``x data``, ``y data``, ``xy data``

Anything else raises :class:`ValueError` with a message the plot test
turns into a student-facing failure; PR E (the language guard) refuses
these props for ``language="octave"`` up front so this branch is only
hit when an unrecognised prop slips through.
"""

from __future__ import annotations

from collections import namedtuple

import matplotlib.colors as mcolors
import numpy as np

# Public re-export so callers can compare to Python's return type.
Points = namedtuple("Points", ["x", "y"])

# Properties this module knows how to extract.  Kept as a public
# constant so PR E's language guard can consult the same list.
SUPPORTED_PROPS = frozenset(
    {
        "title",
        "x label",
        "y label",
        "x limits",
        "y limits",
        "x tick labels",
        "y tick labels",
        "number of lines",
        "line colors",
        "x data",
        "y data",
        "xy data",
    }
)


def _primary_axes(test, artifact):
    """Return the payload for the first drawing axes in the first figure.

    ``artifact`` is the JSON payload produced by the Octave runtime
    (or ``None`` when no figures existed at capture time).  We match
    :func:`generic_grader.utils.plot.get_current_axes` by failing the
    test with a student-facing message when no axes are found — the
    Python side raises the same "make sure your code produces a plot"
    text.
    """
    figures = (artifact or {}).get("figures") or []
    for figure in figures:
        axes_list = figure.get("axes") or []
        for ax in axes_list:
            return ax
    test.fail(
        "Cannot find the figure's axes."
        " Make sure your code produces a plot of some type."
    )


def _lines(test, artifact):
    """Return the list of line payloads on the primary axes.

    Kept separate from :func:`_primary_axes` because most callers want
    the whole list; a few want just the axes-level scalars.
    """
    ax = _primary_axes(test, artifact)
    return ax.get("lines") or []


def _line_or_fail(test, artifact, index):
    """Return the ``index``-th line payload or fail like the Python side.

    The Python ``get_x_data`` / ``get_y_data`` helpers raise ``IndexError``
    which the ``@weighted`` decorator turns into an assertion failure
    with the message "Failed to find x/y data for data set N".  We
    reproduce the same message so the failure text is identical.
    """
    lines = _lines(test, artifact)
    if index < 0 or index >= len(lines):
        test.failureException = IndexError
        test.fail(f"Failed to find x data for data set {index + 1}.")
    return lines[index]


def _color_to_name(rgb):
    """Convert an ``[r, g, b]`` triple to a matplotlib named colour.

    Falls back to an ``(r, g, b, 1.0)`` tuple when no named colour
    matches — mirroring
    :func:`generic_grader.utils.plot.get_line_colors` so ``line colors``
    comparisons produce the same string vs tuple types on both sides.
    """
    named_colors = sorted(mcolors.get_named_colors_mapping().items())
    triple = tuple(float(c) for c in rgb)
    for name, color in named_colors:
        if mcolors.same_color(color, triple):
            return name
    return mcolors.to_rgba(triple)


def get_property(test, artifact, prop, kwargs):
    """Extract ``prop`` from an Octave runtime plot artifact.

    Signature mirrors :func:`generic_grader.utils.plot.get_property`
    with an extra ``artifact`` parameter so we don't need to touch
    the Python dispatcher.  The caller (typically
    :mod:`generic_grader.image.plot_prop_matches_reference`) passes
    ``self.ref_user.artifacts.get("plot")`` or
    ``self.student_user.artifacts.get("plot")``.
    """
    kwargs = kwargs or {}
    if prop == "title":
        return _primary_axes(test, artifact).get("title", "")
    if prop == "x label":
        return _primary_axes(test, artifact).get("xlabel", "")
    if prop == "y label":
        return _primary_axes(test, artifact).get("ylabel", "")
    if prop == "x limits":
        # ``matplotlib`` returns a tuple; the JSON payload gives us a
        # list.  Convert so ``assertEqual`` treats the two the same
        # way it did before.
        return tuple(_primary_axes(test, artifact).get("xlim", []))
    if prop == "y limits":
        return tuple(_primary_axes(test, artifact).get("ylim", []))
    if prop == "x tick labels":
        return list(_primary_axes(test, artifact).get("xticklabels", []))
    if prop == "y tick labels":
        return list(_primary_axes(test, artifact).get("yticklabels", []))
    if prop == "number of lines":
        return len(_lines(test, artifact))
    if prop == "line colors":
        return [
            _color_to_name(ln.get("color", [0, 0, 0])) for ln in _lines(test, artifact)
        ]
    if prop == "x data":
        index = kwargs.get("index", 0)
        return list(_line_or_fail(test, artifact, index).get("xdata", []))
    if prop == "y data":
        index = kwargs.get("index", 0)
        return [
            round(v, 6) for v in _line_or_fail(test, artifact, index).get("ydata", [])
        ]
    if prop == "xy data":
        index = kwargs.get("index", 0)
        line = _line_or_fail(test, artifact, index)
        return Points(
            np.array(line.get("xdata", []), dtype=float),
            np.array(line.get("ydata", []), dtype=float),
        )
    raise ValueError(
        f"Property `{prop}` is not supported by the Octave plot runtime."
        " Check `generic_grader.utils.octave_plot.SUPPORTED_PROPS` for the"
        ' list of properties that work with `language="octave"`.'
    )


__all__ = ("Points", "SUPPORTED_PROPS", "get_property")
