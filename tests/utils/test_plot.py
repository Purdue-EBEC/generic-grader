import datetime
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import matplotlib as mpl
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pytest

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
    get_pie_wedges,
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


@pytest.fixture
def setup_line_plot():
    """Fixture for setting up a simple line plot."""
    fig, ax = plt.subplots()
    ax.plot(
        [x for x in range(10)], [y for y in range(10)], label="Line", color="#4A90E2"
    )
    ax.set_xlim(0, 99)
    ax.set_ylim(0, 99)
    ax.set_xticks([x for x in range(10)], [str(x) for x in range(10)])
    ax.set_yticks([y for y in range(10)], [str(y) for y in range(10)])
    ax.set_xlabel("X Label")
    ax.set_ylabel("Y Label")
    ax.set_title("Title")
    ax.legend(["Line 1"])
    ax.spines["top"].set_visible(False)
    ax.spines["bottom"].set_position("zero")
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_position("zero")
    yield ax
    plt.close(fig)


@pytest.fixture
def setup_line_plot_two():
    """Fixture for setting up a simple line plot with two lines."""
    fig, ax = plt.subplots()
    ax.plot([x for x in range(10)], [y for y in range(10)], label="Line", color="red")
    ax.plot(
        [x for x in range(20)], [y + 1 for y in range(20)], label="Line 2", color="blue"
    )
    yield ax
    plt.close(fig)


@pytest.fixture
def setup_bar_chart():
    """Fixture for setting up a simple bar chart."""
    fig, ax = plt.subplots()
    ax.bar([0, 1], [1, 2])
    yield ax
    plt.close(fig)


@pytest.fixture
def setup_pie_chart():
    """Fixture for setting up a simple pie chart."""
    fig, ax = plt.subplots()
    ax.pie([1, 2, 3], labels=["A", "B", "C"], colors=["red", "green", "blue"])
    yield ax
    plt.close(fig)


@pytest.fixture
def setup_time_chart():
    """Fixture for setting up a simple time series chart."""
    fig, ax = plt.subplots()
    time_data = [datetime.date(2000, 1, x) for x in range(1, 6)]
    ax.bar(time_data, range(5))
    yield ax, time_data
    plt.close(fig)


class MockTest(unittest.TestCase):
    """Fake test class for testing the plot functions."""


def test_get_current_axes(setup_line_plot):
    """Test that the get_current_axes function returns the correct axes."""
    axes_list = get_current_axes(MockTest())
    assert len(axes_list) == 1
    assert axes_list[0] == setup_line_plot


def test_missing_axes():
    """Test that an error is raised when the figure has no axes."""
    with pytest.raises(AssertionError) as exc_info:
        get_current_axes(MockTest())
    assert (
        "Cannot find the figure's axes. Make sure your code produces a plot of some type."
        in str(exc_info.value)
    )


def test_get_pie_wedges(setup_pie_chart):
    """Test that the get_pie_wedges function returns the correct wedges."""
    wedges = get_pie_wedges(MockTest())
    assert len(wedges) == 3
    assert all(isinstance(w, patches.Wedge) for w in wedges)


def test_empty_pie(setup_line_plot):
    """Test that an error is raised when the figure has no pie wedges."""
    with pytest.raises(AssertionError) as exc_info:
        get_pie_wedges(MockTest())
    assert (
        "Cannot find any pie wedges in your figure."
        " Make sure your code produces a pie chart."
    ) == str(exc_info.value)


def test_get_pie_wedge_labels(setup_pie_chart):
    """Test that the get_pie_wedge_labels function returns the correct labels."""
    labels = get_pie_wedge_labels(MockTest())
    assert labels == ["A", "B", "C"]


def test_get_pie_wedge_colors(setup_pie_chart):
    """Test that the get_pie_wedge_colors function returns the correct colors."""
    colors = get_pie_wedge_colors(MockTest())
    expected_colors = [mpl.colors.to_hex(color) for color in ["red", "green", "blue"]]
    assert colors == expected_colors


def test_get_pie_wedge_angles(setup_pie_chart):
    """Test that the get_pie_wedge_angles function returns the correct angles."""
    angles = get_pie_wedge_angles(MockTest())
    expected_angles = [
        np.float32(x) for x in (60, 120, 180)
    ]  # Calculated based on data proportions
    assert angles == expected_angles


def test_get_number_lines(setup_line_plot):
    """Test that the get_number_lines function returns the correct number of lines."""
    assert get_number_lines(MockTest()) == 1


def test_get_number_lines_two(setup_line_plot_two):
    """Test that the get_number_lines function returns the correct number of lines."""
    assert get_number_lines(MockTest()) == 2


def test_get_number_bars(setup_bar_chart):
    """Test that the get_number_bars function returns the correct number of bars."""
    assert get_number_bars(MockTest()) == 2


def test_empty_get_bar_number(setup_pie_chart):
    """Test that an error is raised when the figure has no bars."""
    with pytest.raises(AssertionError) as exc_info:
        get_number_bars(MockTest())
    assert (
        "Failed to find a bar chart. Make sure your code produces a bar chart."
        in str(exc_info.value)
    )


def test_get_bar_widths(setup_bar_chart):
    """Test that the get_bar_widths function returns the correct bar widths."""
    widths = get_bar_widths(MockTest())
    expected_widths = [setup_bar_chart.patches[i].get_width() for i in range(2)]
    assert widths == expected_widths


def test_empty_get_bar_widths(setup_pie_chart):
    """Test that an error is raised when the figure has no bars."""
    with pytest.raises(AssertionError) as exc_info:
        get_bar_widths(MockTest())
    assert (
        "Failed to find a bar chart. Make sure your code produces a bar chart."
        in str(exc_info.value)
    )


def test_get_line_colors(setup_line_plot):
    """Test that the get_line_colors function returns the correct colors."""
    colors = get_line_colors(MockTest())
    expected_colors = [
        (0.2901960784313726, 0.5647058823529412, 0.8862745098039215, 1.0)
    ]
    assert colors == expected_colors


def test_get_line_colors_two(setup_line_plot_two):
    """Test that the get_line_colors function returns the correct colors."""
    colors = get_line_colors(MockTest())
    expected_colors = ["r", "b"]
    assert colors == expected_colors


def test_get_xy_data(setup_line_plot):
    """Test that the get_xy_data function returns the correct x and y data."""
    points = get_xy_data(MockTest())
    expected_x = np.array([x for x in range(10)])
    expected_y = np.array([y for y in range(10)])

    assert np.array_equal(points.x, expected_x)
    assert np.array_equal(points.y, expected_y)


def test_get_x_data_one_line(setup_line_plot):
    """Test that the get_x_data function returns the correct x data for a single line plot."""
    x_data = get_x_data(MockTest())
    expected_x = [x for x in range(10)]

    assert x_data == expected_x


def test_get_x_data_two_lines(setup_line_plot_two):
    """Test that the get_x_data function returns the correct x data for a multi-line plot."""
    x_data = get_x_data(MockTest(), 1)
    expected_x = [x for x in range(20)]

    assert x_data == expected_x


def test_get_x_data_bar(setup_bar_chart):
    """Test that the get_x_data function returns the correct x data for a bar chart."""
    x_data = get_x_data(MockTest())
    expected_x = [np.float64(x) for x in (0, 1)]

    assert x_data == expected_x


def test_get_x_data_missing_line(setup_line_plot):
    """Test that an error is raised when the data set is not found."""
    with pytest.raises(AssertionError) as exc_info:
        get_x_data(MockTest(), 1)
    assert "Failed to find x data for data set 2." == str(exc_info.value)


def test_x_time_data(setup_time_chart):
    """Test that the get_x_time_data function returns the correct x data for a time chart."""
    x_data = get_x_time_data(MockTest())
    expected_x = [datetime.date(2000, 1, x) for x in range(1, 6)]
    assert x_data == expected_x


def test_get_y_data(setup_line_plot):
    """Test that the get_y_data function returns the correct y data."""
    y_data = get_y_data(MockTest())
    expected_y = [y for y in range(10)]

    assert y_data == expected_y


def test_get_y_data_two_lines(setup_line_plot_two):
    """Test that the get_y_data function returns the correct y data for a multi-line plot."""
    y_data = get_y_data(MockTest(), 1)
    expected_y = [y + 1 for y in range(20)]

    assert y_data == expected_y


def test_get_y_data_bar(setup_bar_chart):
    """Test that the get_y_data function returns the correct y data for a bar chart."""
    y_data = get_y_data(MockTest())
    expected_y = [np.int64(x) for x in (1, 2)]

    assert y_data == expected_y


def test_get_y_data_missing_line(setup_line_plot):
    """Test that an error is raised when the data set is not found."""
    with pytest.raises(AssertionError) as exc_info:
        get_y_data(MockTest(), 1)
    assert "Failed to find y data for line 2." == str(exc_info.value)


def test_get_x_limits(setup_line_plot):
    """Test that the get_x_limits function returns the correct x limits."""
    xlim = get_x_limits(MockTest())
    expected_xlim = (0.0, 99.0)

    assert xlim == expected_xlim


def test_get_y_limits(setup_line_plot):
    """Test that the get_y_limits function returns the correct y limits."""
    ylim = get_y_limits(MockTest())
    expected_ylim = (0.0, 99.0)

    assert ylim == expected_ylim


def test_get_x_tick_labels(setup_line_plot):
    """Test that the get_x_tick_labels function returns the correct x tick labels."""
    labels = get_x_tick_labels(MockTest())
    expected_labels = [str((label)) for label in range(10)]

    assert labels == expected_labels


def test_get_y_tick_labels(setup_line_plot):
    """Test that the get_y_tick_labels function returns the correct y tick labels."""
    labels = get_y_tick_labels(MockTest())
    expected_labels = [str(int(label)) for label in range(10)]

    assert labels == expected_labels


def test_get_x_label(setup_line_plot):
    """Test that the get_x_label function returns the correct x label."""
    assert get_x_label(MockTest()) == "X Label"


def test_get_y_label(setup_line_plot):
    """Test that the get_y_label function returns the correct y label."""
    assert get_y_label(MockTest()) == "Y Label"


def test_get_grid_lines(setup_line_plot):
    """Test that the get_grid_lines function returns the correct grid lines."""
    # Enable the grid lines on the plot
    setup_line_plot.grid(True)

    # Retrieve the grid lines using the function
    lines = get_grid_lines(MockTest())

    # Get expected grid lines directly from the plot
    expected_x_lines = [
        line.get_path().vertices
        for line in setup_line_plot.get_xaxis().get_gridlines()
        if line.get_visible()
    ]
    expected_y_lines = [
        line.get_path().vertices
        for line in setup_line_plot.get_yaxis().get_gridlines()
        if line.get_visible()
    ]

    # Convert numpy arrays to tuples for comparison
    expected_x_lines = [tuple(map(tuple, line)) for line in expected_x_lines]
    expected_y_lines = [tuple(map(tuple, line)) for line in expected_y_lines]

    # Combine x and y grid lines into a single list
    expected_lines = expected_x_lines + expected_y_lines

    # Assert that the retrieved lines match the expected lines
    assert len(lines) == len(expected_lines)
    for line in lines:
        assert line in expected_lines


def test_get_title(setup_line_plot):
    """Test that the get_title function returns the correct title."""
    assert get_title(MockTest()) == "Title"


def test_get_legend(setup_line_plot):
    """Test that the get_legend function returns the correct legend."""
    assert get_legend(MockTest()) == ["Line 1"]


def test_get_spine_visibility(setup_line_plot):
    """Test that the get_spine_visibility function returns the correct spine visibility."""
    visibility = get_spine_visibility(pytest)
    assert visibility["top"] is False and visibility["right"] is False
    assert visibility["bottom"] and visibility["left"]


def test_get_spine_positions(setup_line_plot):
    """Test that the get_spine_positions function returns the correct spine positions."""
    positions = get_spine_positions(pytest)
    assert positions["bottom"] == "zero" and positions["left"] == "zero"


prop_cases = [
    {
        "prop": "number of lines",
        "func_name": "get_number_lines",
    },
    {
        "prop": "number of bars",
        "func_name": "get_number_bars",
    },
    {
        "prop": "bar widths",
        "func_name": "get_bar_widths",
    },
    {
        "prop": "line colors",
        "func_name": "get_line_colors",
    },
    {
        "prop": "xy data",
        "func_name": "get_xy_data",
    },
    {
        "prop": "x data",
        "func_name": "get_x_data",
    },
    {
        "prop": "x time data",
        "func_name": "get_x_time_data",
    },
    {
        "prop": "y data",
        "func_name": "get_y_data",
    },
    {
        "prop": "x limits",
        "func_name": "get_x_limits",
    },
    {
        "prop": "y limits",
        "func_name": "get_y_limits",
    },
    {
        "prop": "x tick labels",
        "func_name": "get_x_tick_labels",
    },
    {
        "prop": "y tick labels",
        "func_name": "get_y_tick_labels",
    },
    {
        "prop": "x label",
        "func_name": "get_x_label",
    },
    {
        "prop": "y label",
        "func_name": "get_y_label",
    },
    {
        "prop": "wedge labels",
        "func_name": "get_pie_wedge_labels",
    },
    {
        "prop": "wedge colors",
        "func_name": "get_pie_wedge_colors",
    },
    {
        "prop": "wedge angles",
        "func_name": "get_pie_wedge_angles",
    },
    {
        "prop": "title",
        "func_name": "get_title",
    },
    {
        "prop": "grid lines",
        "func_name": "get_grid_lines",
    },
    {
        "prop": "legend",
        "func_name": "get_legend",
    },
    {
        "prop": "spine visibility",
        "func_name": "get_spine_visibility",
    },
    {
        "prop": "position of each spine",
        "func_name": "get_spine_positions",
    },
]
func_names = [case["func_name"] for case in prop_cases]


@pytest.mark.parametrize("case", prop_cases)
def test_get_property(case):
    """Test that the get_property function returns the correct property."""
    with ExitStack() as stack:
        for func_name in func_names:
            if func_name == case["func_name"]:
                stack.enter_context(
                    patch(f"generic_grader.utils.plot.{func_name}", lambda x: True)
                )
            else:
                stack.enter_context(
                    patch(f"generic_grader.utils.plot.{func_name}", lambda x: False)
                )

        assert get_property(MockTest(), case["prop"], {}) is True


def test_get_property_default():
    """Test that the get_property function returns the default value when the property is not found."""
    with pytest.raises(ValueError) as exc_info:
        get_property(MockTest(), "invalid property", {})
    assert (
        "Unknown property `invalid property`. This is a result of a misconfigured config file. Please contact your instructor."
    ) == str(exc_info.value)
