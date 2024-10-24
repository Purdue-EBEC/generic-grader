from collections import namedtuple

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


def get_current_axes(test):
    """Find and return a list of axes in the current figure."""

    # Get the axes from the current figure (creates figure if none exists).
    axes_list = plt.gcf().get_axes()

    if not axes_list:
        # Axes list is empty.
        test.fail(
            "Cannot find the figure's axes."
            " Make sure your code produces a plot of some type."
        )

    return axes_list


def get_pie_wedges(test):
    """Find and return any wedge patches in the current axes."""

    # Get the list of patches in the first set of axes.
    patches = get_current_axes(test)[0].patches

    # Filter patches to include only wedges."
    wedges = [p for p in patches if isinstance(p, mpl.patches.Wedge)]

    if not wedges:
        # Axes list is empty.
        test.fail(
            "Cannot find any pie wedges in your figure."
            " Make sure your code produces a pie chart."
        )

    return wedges


def get_pie_wedge_labels(test):
    """Find and return a list of labels for any wedge patches in the current
    axes."""

    wedges = get_pie_wedges(test)
    return [w.get_label() for w in wedges]


def get_pie_wedge_colors(test):
    """Find and return a list of wedge colors for any wedge patches in the
    current axes."""

    wedges = get_pie_wedges(test)
    return [mpl.colors.to_hex(w.get_facecolor()) for w in wedges]


def get_pie_wedge_angles(test):
    """Find and return a list of wedge angles for any wedge patches in the
    current axes."""

    wedges = get_pie_wedges(test)
    return [round(w.theta2 - w.theta1, 4) for w in wedges]


def get_number_lines(test):
    """Find and return the number of lines on the current axes."""
    return len(get_current_axes(test)[0].get_lines())


def get_number_bars(test):
    """Find and return the number of bars in the bar chart."""
    ax = get_current_axes(test)[0]

    # Count the number of bar chart bars.
    nbars = 0
    containers = ax.containers
    if containers and isinstance(containers[0], mpl.container.BarContainer):
        # Find the chart's bars
        nbars = sum(isinstance(p, mpl.patches.Rectangle) for p in containers[0].patches)

    if nbars == 0:
        test.fail(
            "Failed to find a bar chart. Make sure your code produces a bar chart."
        )

    return nbars


def get_bar_widths(test):
    """Find and return a list of widths for each bar in the bar chart."""
    ax = get_current_axes(test)[0]

    # Count the number of bar chart bars.
    containers = ax.containers
    widths = []
    if containers and isinstance(containers[0], mpl.container.BarContainer):
        # Find the chart's bars
        for patch in containers[0].patches:
            if isinstance(patch, mpl.patches.Rectangle):
                widths.append(patch.get_width())

    if len(widths) == 0:
        test.fail(
            "Failed to find a bar chart. Make sure your code produces a bar chart."
        )

    return widths


def get_line_colors(test):
    """Find and return the colors of the lines on the current axes."""
    lines = get_current_axes(test)[0].get_lines()
    named_colors = sorted(mpl.colors.get_named_colors_mapping().items())
    colors = []
    for line in lines:
        for name, color in named_colors:
            if mpl.colors.same_color(color, line.get_color()):
                colors.append(name)
                break  # stop after finding the first named color match
        else:
            colors.append(mpl.colors.to_rgba(line.get_color()))
    return colors


def get_xy_data(test, index=0):
    """Find and return a list of xy data points."""
    x_data = get_x_data(test, index)
    y_data = get_y_data(test, index)
    Points = namedtuple("Points", ["x", "y"])
    return Points(np.array(x_data), np.array(y_data))


def get_x_data(test, index=0):
    """Find and return a list of x data points."""
    ax = get_current_axes(test)[0]

    # Check if the axes contain a bar chart.
    containers = ax.containers
    if containers and isinstance(containers[0], mpl.container.BarContainer):
        # Find the chart's bars
        date_nums = [p.get_x() + p.get_width() / 2 for p in containers[0].patches]
        return date_nums

    # Handle line plots.
    try:
        return list(ax.get_lines()[index].get_xdata())
    except IndexError:
        msg = f"Failed to find x data for data set {index + 1}."

    if msg:
        test.fail(msg)


def get_x_time_data(test):
    """Find and return a list of x data points as times."""
    nums = get_x_data(test)

    # Covert the matplotlib dates to `datetime.date` objects
    return [mpl.dates.num2date(num).date() for num in nums]


def get_y_data(test, index=0):
    """Find and return a list of y data points."""

    ax = get_current_axes(test)[0]

    # Check if the axes contain a bar chart.
    containers = ax.containers
    if containers and isinstance(containers[0], mpl.container.BarContainer):
        return [round(v, 6) for v in containers[0].datavalues]

    # Handle line plots.
    try:
        return [round(v, 6) for v in ax.get_lines()[index].get_ydata()]
    except IndexError:
        msg = f"Failed to find y data for line {index + 1}."

    if msg:
        test.fail(msg)


def get_x_limits(test):
    """Find and return the x limits of the plot."""
    return get_current_axes(test)[0].get_xlim()


def get_y_limits(test):
    """Find and return the y limits of the plot."""
    return get_current_axes(test)[0].get_ylim()


def get_x_tick_labels(test):
    """Find and return the x tick labels of the plot."""
    ax = get_current_axes(test)[0]

    # Force pyplot to produce the labels
    plt.gcf().canvas.draw()

    return [label.get_text() for label in ax.get_xticklabels()]


def get_y_tick_labels(test):
    """Find and return the y tick labels of the plot."""
    ax = get_current_axes(test)[0]

    # Force pyplot to produce the labels
    plt.gcf().canvas.draw()

    return [label.get_text() for label in ax.get_yticklabels()]


def get_x_label(test):
    """Find and return the x label of the plot."""
    return get_current_axes(test)[0].get_xlabel()


def get_y_label(test):
    """Find and return the y label of the plot."""
    return get_current_axes(test)[0].get_ylabel()


def get_grid_lines(test):
    """Find and return the visible grid lines of the current axes as a list of
    line tuples of vertex tuples."""
    plt.gcf().canvas.draw()

    axes = get_current_axes(test)[0]
    x_gridlines = axes.get_xaxis().get_gridlines()
    y_gridlines = axes.get_yaxis().get_gridlines()

    x_lines = [line.get_path().vertices for line in x_gridlines if line.get_visible()]
    y_lines = [line.get_path().vertices for line in y_gridlines if line.get_visible()]

    # Convert lines from numpy 2d arrays to tuple of tuples
    x_lines = [tuple(map(tuple, line)) for line in x_lines]
    y_lines = [tuple(map(tuple, line)) for line in y_lines]

    # Filter lines outside of the axes window.
    lines = []
    xmin, xmax = axes.get_xlim()
    ymin, ymax = axes.get_ylim()
    for line in x_lines:
        x = line[0][0]
        if xmin <= x <= xmax:
            lines.append(line)

    for line in y_lines:
        y = line[0][1]
        if ymin <= y <= ymax:
            lines.append(line)

    return lines


def get_title(test):
    """Find and return the title of the current axes."""
    return get_current_axes(test)[0].title.get_text()


def get_legend(test):
    """Find and return the legend labels of the current axes."""
    legend = get_current_axes(test)[0].get_legend()

    return [t.get_text() for t in legend.texts] if legend else None


def get_spine_visibility(test):
    """Find and return the visibility of each spine.  A spine is visible when
    the visible flag is set and the line width is greater than zero and the
    alpha channel is greater than zero.
    """
    visibility = {}
    for name, spine in get_current_axes(test)[0].spines.items():
        visible = spine.get_visible()
        linewidth = spine.get_linewidth()
        alpha_channel = spine.get_edgecolor()[3]
        visibility[name] = bool(visible and linewidth and alpha_channel)

    return visibility


def get_spine_positions(test):
    """Find and return the position of each spine.  The positions ('data', 0.0)
    and 'zero' produce the same result, but are currently not considered equal
    for this test.
    """
    positions = {}
    for name, spine in get_current_axes(test)[0].spines.items():
        positions[name] = spine.get_position()

    return positions


def get_property(test, prop, kwargs):
    if prop == "number of lines":
        return get_number_lines(test)
    elif prop == "number of bars":
        return get_number_bars(test)
    elif prop == "bar widths":
        return get_bar_widths(test)
    elif prop == "line colors":
        return get_line_colors(test)
    elif prop == "xy data":
        return get_xy_data(test, **kwargs)
    elif prop == "x data":
        return get_x_data(test, **kwargs)
    elif prop == "x time data":
        return get_x_time_data(test)
    elif prop == "y data":
        return get_y_data(test, **kwargs)
    elif prop == "x limits":
        return get_x_limits(test)
    elif prop == "y limits":
        return get_y_limits(test)
    elif prop == "x tick labels":
        return get_x_tick_labels(test)
    elif prop == "y tick labels":
        return get_y_tick_labels(test)
    elif prop == "x label":
        return get_x_label(test)
    elif prop == "y label":
        return get_y_label(test)
    elif prop == "wedge labels":
        return get_pie_wedge_labels(test)
    elif prop == "wedge colors":
        return get_pie_wedge_colors(test)
    elif prop == "wedge angles":
        return get_pie_wedge_angles(test)
    elif prop == "title":
        return get_title(test)
    elif prop == "grid lines":
        return get_grid_lines(test)
    elif prop == "legend":
        return get_legend(test)
    elif prop == "spine visibility":
        return get_spine_visibility(test)
    elif prop == "position of each spine":
        return get_spine_positions(test)
    else:
        raise ValueError(
            f"Unknown property `{prop}`. This is a result of a misconfigured config file. Please contact your instructor."
        )
