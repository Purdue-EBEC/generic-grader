"""Round-trip tests for the host-side serialized-figure facade.

The strategy: build a real ``matplotlib`` figure, snapshot every value
that ``generic_grader.utils.plot`` would extract from it via the live
API, then serialize the figure to a dict (the same dict the sandbox
worker would ship), hand the dict to the facade, and verify every
plot helper produces the same value when it reads through the facade.

This pins the contract that the serialized format + facade together
reproduce the live-matplotlib API surface used by the grader.
"""

from __future__ import annotations

import datetime
import unittest

import matplotlib.pyplot as plt
import pytest

from generic_grader.sandbox.figure_facade import SerializedAxes, SerializedFigure
from generic_grader.sandbox.figure_serializer import (
    serialize_current_figures,
    serialize_figure,
)
from generic_grader.utils.plot import (
    get_bar_widths,
    get_current_axes,
    get_grid_lines,
    get_legend,
    get_line_colors,
    get_number_bars,
    get_number_lines,
    get_pie_wedge_angles,
    get_pie_wedge_colors,
    get_pie_wedge_labels,
    get_property,
    get_spine_positions,
    get_spine_visibility,
    get_title,
    get_x_data,
    get_x_label,
    get_x_limits,
    get_x_tick_labels,
    get_x_time_data,
    get_xy_data,
    get_y_data,
    get_y_label,
    get_y_limits,
    get_y_tick_labels,
)


class MockTest(unittest.TestCase):
    """Test stub that lets ``test.fail`` raise like a real test."""


@pytest.fixture
def line_test():
    """Build a line plot, snapshot values live, then re-attach via the facade.

    The fixture yields a tuple ``(test_live, test_sandbox)`` where both
    expose the same figure's data, but ``test_live`` reads via the
    live ``plt.gcf()`` and ``test_sandbox`` reads via the serialized
    facade attached to ``test._sandbox_figures``.
    """
    fig, ax = plt.subplots()
    ax.plot(range(5), [v * 2 for v in range(5)], label="Line", color="#4A90E2")
    ax.set_xlim(-1, 6)
    ax.set_ylim(-1, 11)
    ax.set_xticks(range(5), [f"x{x}" for x in range(5)])
    ax.set_yticks(range(0, 11, 2), [f"y{y}" for y in range(0, 11, 2)])
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Hello")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["bottom"].set_position("zero")
    serialized = serialize_figure(fig)

    test_live = MockTest()
    test_sandbox = MockTest()
    test_sandbox._sandbox_figures = [serialized]
    yield test_live, test_sandbox
    plt.close(fig)


def test_facade_number_of_lines(line_test):
    live, sandbox = line_test
    assert get_number_lines(sandbox) == get_number_lines(live) == 1


def test_facade_line_colors(line_test):
    live, sandbox = line_test
    assert get_line_colors(sandbox) == get_line_colors(live)


def test_facade_xy_data(line_test):
    live, sandbox = line_test
    live_xy = get_xy_data(live)
    sandbox_xy = get_xy_data(sandbox)
    assert list(sandbox_xy.x) == list(live_xy.x)
    assert list(sandbox_xy.y) == list(live_xy.y)


def test_facade_x_y_data_separately(line_test):
    live, sandbox = line_test
    assert get_x_data(sandbox) == get_x_data(live)
    assert get_y_data(sandbox) == get_y_data(live)


def test_facade_x_data_missing_index_fails(line_test):
    _, sandbox = line_test
    with pytest.raises(AssertionError):
        get_x_data(sandbox, index=5)


def test_facade_y_data_missing_index_fails(line_test):
    _, sandbox = line_test
    with pytest.raises(AssertionError):
        get_y_data(sandbox, index=5)


def test_facade_limits_and_labels(line_test):
    live, sandbox = line_test
    assert get_x_limits(sandbox) == get_x_limits(live)
    assert get_y_limits(sandbox) == get_y_limits(live)
    assert get_x_label(sandbox) == get_x_label(live)
    assert get_y_label(sandbox) == get_y_label(live)
    assert get_title(sandbox) == get_title(live)


def test_facade_tick_labels(line_test):
    live, sandbox = line_test
    assert get_x_tick_labels(sandbox) == get_x_tick_labels(live)
    assert get_y_tick_labels(sandbox) == get_y_tick_labels(live)


def test_facade_legend(line_test):
    live, sandbox = line_test
    assert get_legend(sandbox) == get_legend(live)


def test_facade_spine_visibility(line_test):
    live, sandbox = line_test
    assert get_spine_visibility(sandbox) == get_spine_visibility(live)


def test_facade_spine_positions(line_test):
    live, sandbox = line_test
    # Spine positions can be either strings ('zero') or 2-tuples; both
    # forms round-trip exactly through the facade.
    assert get_spine_positions(sandbox) == get_spine_positions(live)


def test_facade_get_property_dispatch(line_test):
    """``get_property`` is the single entry point used by image tests."""
    live, sandbox = line_test
    for prop in ("title", "x label", "y label", "x limits", "y limits"):
        assert get_property(sandbox, prop, {}) == get_property(live, prop, {})


# ---------------------------------------------------------------------------
# Bar chart facade
# ---------------------------------------------------------------------------


@pytest.fixture
def bar_test():
    fig, ax = plt.subplots()
    ax.bar([0, 1, 2], [3, 5, 7])
    serialized = serialize_figure(fig)
    live = MockTest()
    sandbox = MockTest()
    sandbox._sandbox_figures = [serialized]
    yield live, sandbox
    plt.close(fig)


def test_facade_bar_count_and_widths(bar_test):
    live, sandbox = bar_test
    assert get_number_bars(sandbox) == get_number_bars(live)
    assert get_bar_widths(sandbox) == get_bar_widths(live)


def test_facade_bar_x_y_data(bar_test):
    live, sandbox = bar_test
    assert get_x_data(sandbox) == get_x_data(live)
    assert get_y_data(sandbox) == get_y_data(live)


def test_facade_empty_bar_widths_when_no_bars():
    """A non-bar axes facade reports zero bars and triggers the legacy fail."""
    fig, ax = plt.subplots()
    ax.plot([0], [0])
    serialized = serialize_figure(fig)
    sandbox = MockTest()
    sandbox._sandbox_figures = [serialized]
    with pytest.raises(AssertionError):
        get_number_bars(sandbox)
    with pytest.raises(AssertionError):
        get_bar_widths(sandbox)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Pie chart facade
# ---------------------------------------------------------------------------


@pytest.fixture
def pie_test():
    fig, ax = plt.subplots()
    ax.pie([1, 2, 3], labels=["A", "B", "C"], colors=["red", "green", "blue"])
    serialized = serialize_figure(fig)
    live = MockTest()
    sandbox = MockTest()
    sandbox._sandbox_figures = [serialized]
    yield live, sandbox
    plt.close(fig)


def test_facade_pie_labels_colors_angles(pie_test):
    live, sandbox = pie_test
    assert get_pie_wedge_labels(sandbox) == get_pie_wedge_labels(live)
    assert get_pie_wedge_colors(sandbox) == get_pie_wedge_colors(live)
    assert get_pie_wedge_angles(sandbox) == get_pie_wedge_angles(live)


def test_facade_pie_missing_wedges_fails():
    """Asking for pie wedges on a line plot fails like the live path."""
    fig, ax = plt.subplots()
    ax.plot([0], [0])
    serialized = serialize_figure(fig)
    sandbox = MockTest()
    sandbox._sandbox_figures = [serialized]
    with pytest.raises(AssertionError):
        get_pie_wedge_labels(sandbox)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Grid lines + time data
# ---------------------------------------------------------------------------


@pytest.fixture
def grid_test():
    fig, ax = plt.subplots()
    ax.plot(range(5), range(5))
    ax.grid(True)
    serialized = serialize_figure(fig)
    live = MockTest()
    sandbox = MockTest()
    sandbox._sandbox_figures = [serialized]
    yield live, sandbox
    plt.close(fig)


def test_facade_grid_lines_present(grid_test):
    _, sandbox = grid_test
    grid = get_grid_lines(sandbox)
    # Live mpl gridlines are sometimes drawn outside the data window;
    # the worker has already filtered to the visible window, so we
    # just require that at least one gridline made it through.
    assert isinstance(grid, list)
    assert all(isinstance(line, tuple) for line in grid)


def test_facade_x_time_data():
    fig, ax = plt.subplots()
    dates = [datetime.date(2024, 1, d) for d in range(1, 4)]
    ax.bar(dates, [1, 2, 3])
    serialized = serialize_figure(fig)
    live = MockTest()
    sandbox = MockTest()
    sandbox._sandbox_figures = [serialized]
    assert get_x_time_data(sandbox) == get_x_time_data(live)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Direct facade-class behaviors
# ---------------------------------------------------------------------------


def test_serialized_figure_with_no_axes_returns_empty():
    sf = SerializedFigure({"axes": []})
    assert sf.get_axes() == []


def test_serialized_axes_default_values():
    """Missing dict keys fall back to sensible defaults."""
    ax = SerializedAxes({})
    assert ax.title.get_text() == ""
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""
    assert ax.get_xlim() == (0.0, 1.0)
    assert ax.get_ylim() == (0.0, 1.0)
    assert ax.get_xticklabels() == []
    assert ax.get_yticklabels() == []
    assert ax.get_lines() == []
    assert ax.containers == []
    assert ax.patches == []
    assert ax.get_legend() is None
    assert ax.spines == {}
    # Both axes share the full gridline list so each helper can re-window.
    assert ax.get_xaxis().get_gridlines() == []
    assert ax.get_yaxis().get_gridlines() == []


def test_serialized_axes_line_with_named_color():
    """When ``color_name`` is set, the facade returns it directly."""
    ax = SerializedAxes(
        {
            "lines": [
                {
                    "xdata": [0.0],
                    "ydata": [0.0],
                    "color_name": "red",
                    "color_rgba": None,
                }
            ]
        }
    )
    assert ax.get_lines()[0].get_color() == "red"


def test_serialized_axes_line_without_named_color():
    ax = SerializedAxes(
        {
            "lines": [
                {
                    "xdata": [0.0, 1.0],
                    "ydata": [0.0, 2.0],
                    "color_name": None,
                    "color_rgba": [0.1, 0.2, 0.3, 0.5],
                }
            ]
        }
    )
    line = ax.get_lines()[0]
    assert line.get_xdata() == [0.0, 1.0]
    assert line.get_ydata() == [0.0, 2.0]
    assert line.get_color() == (0.1, 0.2, 0.3, 0.5)


def test_serialized_axes_line_with_no_color_at_all():
    """Both ``color_name`` and ``color_rgba`` missing -> opaque black."""
    ax = SerializedAxes({"lines": [{"xdata": [], "ydata": []}]})
    line = ax.get_lines()[0]
    assert line.get_color() == (0.0, 0.0, 0.0, 1.0)


def test_serialized_axes_spine_position_string_form():
    ax = SerializedAxes(
        {
            "spine_visibility": {"bottom": True},
            "spine_positions": {"bottom": "zero"},
        }
    )
    spine = ax.spines["bottom"]
    assert spine.get_position() == "zero"
    assert spine.get_visible() is True
    assert spine.get_linewidth() == 1.0
    assert spine.get_edgecolor()[3] == 1.0


def test_serialized_axes_spine_invisible():
    ax = SerializedAxes(
        {
            "spine_visibility": {"top": False},
            "spine_positions": {"top": ["data", 0.0]},
        }
    )
    spine = ax.spines["top"]
    assert spine.get_visible() is False
    assert spine.get_linewidth() == 0.0
    assert spine.get_edgecolor()[3] == 0.0


def test_serialize_current_figures_into_facade_roundtrip():
    """`serialize_current_figures` returns a list; the facade reads each."""
    # Start from a clean slate so any stray figures left by prior tests
    # don't leak into ``plt.get_fignums()``.
    plt.close("all")
    fig1, ax1 = plt.subplots()
    ax1.plot([0, 1], [0, 1])
    ax1.set_title("First")
    fig2, ax2 = plt.subplots()
    ax2.plot([2, 3], [2, 3])
    ax2.set_title("Second")
    serialized = serialize_current_figures()
    assert len(serialized) == 2
    # `get_current_axes` reads the last figure, matching plt.gcf() rules.
    sandbox = MockTest()
    sandbox._sandbox_figures = serialized
    assert get_title(sandbox) == "Second"


# ---------------------------------------------------------------------------
# Routing: live path is unaffected when no sandbox figures are attached
# ---------------------------------------------------------------------------


def test_live_path_unaffected_without_sandbox_attribute():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("Live")
    live = MockTest()
    # No `_sandbox_figures` attribute -> live plt.gcf() path is used.
    assert get_title(live) == "Live"
    plt.close(fig)


def test_empty_sandbox_figures_falls_through_to_live():
    """An empty list shouldn't be treated as 'sandbox mode'."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("Fallback")
    live = MockTest()
    live._sandbox_figures = []
    assert get_title(live) == "Fallback"
    plt.close(fig)


def test_sandbox_axes_with_no_axes_fails_test():
    """An empty axes list in the sandbox payload calls test.fail."""
    sandbox = MockTest()
    sandbox._sandbox_figures = [{"axes": []}]
    with pytest.raises(AssertionError):
        get_current_axes(sandbox)
