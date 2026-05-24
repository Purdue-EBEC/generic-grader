"""Tests for the matplotlib figure serializer.

The serializer produces a JSON-safe dict capturing every property the
existing `utils/plot.py` extracts from a live `plt.gcf()`. The plan
for commit 6 is to teach `utils/plot.py` to read from this dict so
the grader no longer needs the original Figure object after the
sandbox subprocess exits.

These tests build representative figures (line, bar, pie, mixed,
multi-line, multi-axes), serialize them, and assert the resulting
dict supports the full set of properties.
"""

import json

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

from generic_grader.sandbox.figure_serializer import serialize_figure  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _close_all_figures():
    """Guarantee a clean slate for every test."""
    plt.close("all")
    yield
    plt.close("all")


@pytest.fixture
def line_figure():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 5, 6], color="red", label="series A")
    ax.plot([1, 2, 3], [7, 8, 9], color="blue", label="series B")
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.set_title("Two lines")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 10)
    ax.legend()
    ax.grid(True)
    return fig


@pytest.fixture
def bar_figure():
    fig, ax = plt.subplots()
    ax.bar([1, 2, 3], [10, 20, 30], width=0.6)
    ax.set_xlabel("category")
    ax.set_ylabel("count")
    ax.set_title("A bar chart")
    return fig


@pytest.fixture
def pie_figure():
    fig, ax = plt.subplots()
    ax.pie([30, 45, 25], labels=["A", "B", "C"], colors=["red", "green", "blue"])
    ax.set_title("Pie")
    return fig


# ---------------------------------------------------------------------------
# Smoke / JSON safety
# ---------------------------------------------------------------------------


def test_serialize_returns_a_dict(line_figure):
    data = serialize_figure(line_figure)
    assert isinstance(data, dict)


def test_serialize_is_json_safe(line_figure):
    data = serialize_figure(line_figure)
    # Round-trip through JSON to be sure nothing slipped in as a
    # numpy scalar or matplotlib object.
    text = json.dumps(data)
    restored = json.loads(text)
    assert restored == data


def test_serialize_is_json_safe_bar(bar_figure):
    data = serialize_figure(bar_figure)
    assert json.loads(json.dumps(data)) == data


def test_serialize_is_json_safe_pie(pie_figure):
    data = serialize_figure(pie_figure)
    assert json.loads(json.dumps(data)) == data


def test_serialize_format_version_present(line_figure):
    data = serialize_figure(line_figure)
    assert data["format"] == "matplotlib-figure"
    assert data["version"] == 1


# ---------------------------------------------------------------------------
# Axes structure
# ---------------------------------------------------------------------------


def test_serialize_records_one_axes_per_subplot(line_figure):
    data = serialize_figure(line_figure)
    assert len(data["axes"]) == 1


def test_serialize_records_multiple_axes():
    fig, (ax1, ax2) = plt.subplots(1, 2)
    ax1.plot([1, 2], [3, 4])
    ax2.bar([1, 2], [5, 6])
    data = serialize_figure(fig)
    assert len(data["axes"]) == 2


# ---------------------------------------------------------------------------
# Title / labels / limits
# ---------------------------------------------------------------------------


def test_serialize_captures_title(line_figure):
    data = serialize_figure(line_figure)
    assert data["axes"][0]["title"] == "Two lines"


def test_serialize_captures_x_label(line_figure):
    data = serialize_figure(line_figure)
    assert data["axes"][0]["xlabel"] == "time"


def test_serialize_captures_y_label(line_figure):
    data = serialize_figure(line_figure)
    assert data["axes"][0]["ylabel"] == "value"


def test_serialize_captures_x_limits(line_figure):
    data = serialize_figure(line_figure)
    xlim = data["axes"][0]["xlim"]
    assert xlim == [0.0, 4.0]


def test_serialize_captures_y_limits(line_figure):
    data = serialize_figure(line_figure)
    ylim = data["axes"][0]["ylim"]
    assert ylim == [0.0, 10.0]


def test_serialize_captures_tick_labels(line_figure):
    data = serialize_figure(line_figure)
    # ax.get_xticklabels() only has text after a draw; the serializer
    # is responsible for forcing the draw, exactly like plot.py does.
    xticks = data["axes"][0]["xticklabels"]
    yticks = data["axes"][0]["yticklabels"]
    assert isinstance(xticks, list) and all(isinstance(t, str) for t in xticks)
    assert isinstance(yticks, list) and all(isinstance(t, str) for t in yticks)
    # The line plot covers x=1..3 with xlim=0..4 so there must be
    # at least one visible tick.
    assert any(t.strip() for t in xticks)


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------


def test_serialize_captures_line_count(line_figure):
    data = serialize_figure(line_figure)
    assert len(data["axes"][0]["lines"]) == 2


def test_serialize_captures_line_xdata_and_ydata(line_figure):
    data = serialize_figure(line_figure)
    line0 = data["axes"][0]["lines"][0]
    assert line0["xdata"] == [1.0, 2.0, 3.0]
    assert line0["ydata"] == [4.0, 5.0, 6.0]


def test_serialize_captures_named_color_when_available(line_figure):
    data = serialize_figure(line_figure)
    line0 = data["axes"][0]["lines"][0]
    line1 = data["axes"][0]["lines"][1]
    # Matches the existing plot.get_line_colors behavior: the named-color
    # mapping is sorted alphabetically and the first match wins. 'r' and
    # 'b' (the single-letter aliases) sort before 'red' / 'blue'.
    assert line0["color_name"] in ("r", "red")
    assert line1["color_name"] in ("b", "blue")


def test_serialize_falls_back_to_rgba_for_unnamed_colors():
    fig, ax = plt.subplots()
    # Pick an odd hex color that has no named equivalent.
    ax.plot([1, 2], [3, 4], color="#abcdef")
    data = serialize_figure(fig)
    line = data["axes"][0]["lines"][0]
    assert line["color_name"] is None
    assert line["color_rgba"] is not None
    assert len(line["color_rgba"]) == 4
    assert all(isinstance(c, float) for c in line["color_rgba"])


def test_serialize_x_time_data_uses_dates():
    """Bar/line plots can use matplotlib date numbers on the x axis."""
    import datetime as dt

    fig, ax = plt.subplots()
    dates = [dt.date(2024, 1, d) for d in (1, 2, 3)]
    ax.plot(dates, [10, 20, 30])
    data = serialize_figure(fig)
    line = data["axes"][0]["lines"][0]
    # xdata should be three float matplotlib date numbers; we don't
    # convert here -- commit 6 will read x_time_data by passing each
    # number through mpl.dates.num2date on the host.
    assert len(line["xdata"]) == 3
    assert all(isinstance(v, float) for v in line["xdata"])


# ---------------------------------------------------------------------------
# Bars
# ---------------------------------------------------------------------------


def test_serialize_captures_bars(bar_figure):
    data = serialize_figure(bar_figure)
    bars = data["axes"][0]["bars"]
    assert len(bars) == 3


def test_serialize_captures_bar_widths(bar_figure):
    data = serialize_figure(bar_figure)
    widths = [b["width"] for b in data["axes"][0]["bars"]]
    assert all(abs(w - 0.6) < 1e-9 for w in widths)


def test_serialize_captures_bar_x_centers(bar_figure):
    """x positions = left edge + width/2, matching plot.get_x_data behavior."""
    data = serialize_figure(bar_figure)
    centers = [b["x_center"] for b in data["axes"][0]["bars"]]
    assert centers == [1.0, 2.0, 3.0]


def test_serialize_captures_bar_values(bar_figure):
    """`datavalues` is the canonical source for bar heights."""
    data = serialize_figure(bar_figure)
    values = data["axes"][0]["bar_values"]
    assert values == [10.0, 20.0, 30.0]


def test_serialize_line_axes_have_empty_bar_list(line_figure):
    """A pure line plot has no bars, but the key must still be present."""
    data = serialize_figure(line_figure)
    assert data["axes"][0]["bars"] == []
    assert data["axes"][0]["bar_values"] == []


# ---------------------------------------------------------------------------
# Pie wedges
# ---------------------------------------------------------------------------


def test_serialize_captures_pie_wedges(pie_figure):
    data = serialize_figure(pie_figure)
    wedges = data["axes"][0]["wedges"]
    assert len(wedges) == 3


def test_serialize_captures_pie_wedge_labels(pie_figure):
    data = serialize_figure(pie_figure)
    labels = [w["label"] for w in data["axes"][0]["wedges"]]
    assert labels == ["A", "B", "C"]


def test_serialize_captures_pie_wedge_colors(pie_figure):
    data = serialize_figure(pie_figure)
    colors = [w["color_hex"] for w in data["axes"][0]["wedges"]]
    # to_hex normalizes to lowercase 7-char (#rrggbb) or 9-char (#rrggbbaa)
    assert colors[0].lower().startswith("#")
    assert len(set(colors)) == 3


def test_serialize_captures_pie_wedge_angles(pie_figure):
    data = serialize_figure(pie_figure)
    angles = [w["angle_degrees"] for w in data["axes"][0]["wedges"]]
    # Pie chart angles should sum to 360 (proportional to 30/45/25).
    assert abs(sum(angles) - 360.0) < 1e-3
    # Each angle was rounded to 4 decimal places, matching plot.py.
    for a in angles:
        assert round(a, 4) == a


def test_serialize_line_axes_have_empty_wedge_list(line_figure):
    data = serialize_figure(line_figure)
    assert data["axes"][0]["wedges"] == []


# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------


def test_serialize_captures_legend(line_figure):
    data = serialize_figure(line_figure)
    legend = data["axes"][0]["legend"]
    assert legend == ["series A", "series B"]


def test_serialize_legend_absent_is_none(bar_figure):
    data = serialize_figure(bar_figure)
    assert data["axes"][0]["legend"] is None


# ---------------------------------------------------------------------------
# Grid lines
# ---------------------------------------------------------------------------


def test_serialize_captures_grid_lines(line_figure):
    data = serialize_figure(line_figure)
    grid = data["axes"][0]["grid_lines"]
    # The fixture enabled grid; we expect at least one visible grid line.
    assert len(grid) >= 1
    # Each grid line is a list of [x, y] vertex pairs.
    for line in grid:
        assert isinstance(line, list)
        for vertex in line:
            assert len(vertex) == 2
            assert all(isinstance(c, float) for c in vertex)


def test_serialize_grid_lines_empty_when_grid_off(bar_figure):
    data = serialize_figure(bar_figure)
    # bar_figure didn't enable grid -- grid_lines must be empty
    # (matching plot.get_grid_lines which filters on visibility).
    assert data["axes"][0]["grid_lines"] == []


def test_serialize_grid_lines_filtered_to_axes_window():
    """grid_lines outside xlim/ylim are dropped, exactly like plot.py."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 5, 6])
    ax.set_xlim(1.5, 2.5)
    ax.set_ylim(4.5, 5.5)
    ax.grid(True)
    data = serialize_figure(fig)
    grid = data["axes"][0]["grid_lines"]
    # Every reported gridline must have at least one vertex inside the
    # axes window on the relevant axis.
    for line in grid:
        xs = [v[0] for v in line]
        ys = [v[1] for v in line]
        in_window = any(1.5 <= x <= 2.5 for x in xs) or any(4.5 <= y <= 5.5 for y in ys)
        assert in_window


# ---------------------------------------------------------------------------
# Spines
# ---------------------------------------------------------------------------


def test_serialize_captures_spine_visibility(line_figure):
    data = serialize_figure(line_figure)
    visibility = data["axes"][0]["spine_visibility"]
    # Default matplotlib axes have all four spines visible.
    assert visibility == {"left": True, "right": True, "top": True, "bottom": True}


def test_serialize_reflects_spine_set_invisible():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_linewidth(0)
    data = serialize_figure(fig)
    visibility = data["axes"][0]["spine_visibility"]
    assert visibility["top"] is False
    assert visibility["right"] is False
    assert visibility["left"] is True
    assert visibility["bottom"] is True


def test_serialize_reflects_spine_alpha_zero():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    ax.spines["left"].set_color((0.0, 0.0, 0.0, 0.0))
    data = serialize_figure(fig)
    assert data["axes"][0]["spine_visibility"]["left"] is False


def test_serialize_captures_spine_positions():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    ax.spines["left"].set_position(("data", 0.5))
    ax.spines["bottom"].set_position("zero")
    data = serialize_figure(fig)
    positions = data["axes"][0]["spine_positions"]
    # Position is reported as a 2-tuple [kind, value]. 'zero' is a
    # string-style position which keeps the original string.
    assert positions["left"] == ["data", 0.5]
    assert positions["bottom"] == ["zero", 0.0] or positions["bottom"] == "zero"


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


def test_serialize_figure_with_no_axes():
    fig = plt.figure()
    data = serialize_figure(fig)
    # No axes still produces a well-formed dict with an empty list.
    assert data["axes"] == []


def test_serialize_figure_with_empty_axes():
    fig, ax = plt.subplots()
    data = serialize_figure(fig)
    # Empty axes still produce all keys.
    axes_data = data["axes"][0]
    for key in (
        "title",
        "xlabel",
        "ylabel",
        "xlim",
        "ylim",
        "xticklabels",
        "yticklabels",
        "lines",
        "bars",
        "bar_values",
        "wedges",
        "legend",
        "grid_lines",
        "spine_visibility",
        "spine_positions",
    ):
        assert key in axes_data


def test_serialize_passes_numpy_arrays_through_safely():
    """numpy arrays on either axis must become plain lists of floats."""
    fig, ax = plt.subplots()
    ax.plot(np.array([1, 2, 3]), np.array([4.5, 5.5, 6.5]))
    data = serialize_figure(fig)
    line = data["axes"][0]["lines"][0]
    assert line["xdata"] == [1.0, 2.0, 3.0]
    assert line["ydata"] == [4.5, 5.5, 6.5]
    # No numpy types should survive into the dict.
    for v in line["xdata"] + line["ydata"]:
        assert isinstance(v, float) and not isinstance(v, np.floating)


def test_serialize_handles_object_array_when_date2num_fails(monkeypatch):
    """If date2num refuses an object array, fall back to per-element float()."""
    import matplotlib as _mpl

    fig, ax = plt.subplots()
    # Plot something benign so we have a line to work with.
    ax.plot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])

    def boom(values):
        raise TypeError("refusing to convert")

    monkeypatch.setattr(_mpl.dates, "date2num", boom)

    # Replace the line's xdata with an object array containing a mix
    # of float-convertible and non-convertible values so we exercise
    # both branches of the fallback loop.
    line = ax.get_lines()[0]
    line.set_xdata(np.array([1.5, "oops", 3.5], dtype=object))
    data = serialize_figure(fig)
    xdata = data["axes"][0]["lines"][0]["xdata"]
    # Two valid floats, one NaN.
    assert xdata[0] == 1.5
    assert xdata[2] == 3.5
    # NaN is the substitute for non-coercible values.
    import math

    assert math.isnan(xdata[1])


def test_serialize_bar_container_ignores_non_rectangle_patches(monkeypatch):
    """BarContainer with stray non-Rectangle patches must skip them."""
    fig, ax = plt.subplots()
    bars = ax.bar([1, 2], [3, 4])

    # Inject a non-Rectangle into the bar container's patches list.
    bars.patches = list(bars.patches) + [matplotlib.patches.Circle((0, 0), 0.1)]

    data = serialize_figure(fig)
    # Only the two Rectangle bars are reported; the Circle was skipped.
    assert len(data["axes"][0]["bars"]) == 2


def test_serialize_handles_masked_array_data():
    """matplotlib commonly stores xdata/ydata as numpy MaskedArrays."""
    fig, ax = plt.subplots()
    # Calling ax.plot with a masked array is uncommon; the realistic
    # path is that get_xdata returns a regular ndarray. We still
    # exercise the masked path here to confirm the converter survives.
    mx = np.ma.array([1.0, 2.0, 3.0], mask=[False, True, False])
    my = np.ma.array([4.0, 5.0, 6.0], mask=[False, False, False])
    ax.plot(mx, my)
    data = serialize_figure(fig)
    line = data["axes"][0]["lines"][0]
    assert len(line["xdata"]) == 3
    assert len(line["ydata"]) == 3


# ---------------------------------------------------------------------------
# Integration with the worker
# ---------------------------------------------------------------------------


def test_worker_emits_figure_events(tmp_path):
    """The Python worker should serialize any open figures on success."""
    import textwrap

    from generic_grader.sandbox.protocol import Request
    from generic_grader.sandbox.python_runtime import run_request

    (tmp_path / "submission.py").write_text(
        textwrap.dedent(
            """
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            def main():
                fig, ax = plt.subplots()
                ax.plot([1, 2, 3], [4, 5, 6])
                ax.set_title("hello")
            """
        )
    )
    resp = run_request(
        Request(
            runtime="python",
            submission_dir=str(tmp_path),
            module="submission",
            obj_name="main",
        )
    )
    figs = [e for e in resp.events if e.type == "figure"]
    assert len(figs) == 1
    assert figs[0].properties["axes"][0]["title"] == "hello"


def test_worker_skips_figures_when_not_in_captures(tmp_path):
    """Tests that don't need figures can opt out via captures."""
    import textwrap

    from generic_grader.sandbox.protocol import Request
    from generic_grader.sandbox.python_runtime import run_request

    (tmp_path / "submission.py").write_text(
        textwrap.dedent(
            """
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            def main():
                fig, ax = plt.subplots()
                ax.plot([1], [1])
            """
        )
    )
    resp = run_request(
        Request(
            runtime="python",
            submission_dir=str(tmp_path),
            module="submission",
            obj_name="main",
            captures=("return", "exception"),
        )
    )
    figs = [e for e in resp.events if e.type == "figure"]
    assert figs == []


def test_worker_closes_figures_after_capture(tmp_path):
    """After a run, no figures should leak into the host's pyplot state.

    This matters because the worker process is normally short-lived
    (the isolate runner spawns a fresh one per test), but we exercise
    the in-process path in unit tests and a leaked figure would cause
    surprising interactions between tests.
    """
    import textwrap

    from generic_grader.sandbox.protocol import Request
    from generic_grader.sandbox.python_runtime import run_request

    (tmp_path / "submission.py").write_text(
        textwrap.dedent(
            """
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            def main():
                plt.figure()
                plt.plot([1, 2], [3, 4])
            """
        )
    )
    plt.close("all")
    run_request(
        Request(
            runtime="python",
            submission_dir=str(tmp_path),
            module="submission",
            obj_name="main",
        )
    )
    assert plt.get_fignums() == []
