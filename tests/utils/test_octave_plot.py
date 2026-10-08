"""Unit tests for :mod:`generic_grader.utils.octave_plot`."""

from __future__ import annotations

import unittest

import numpy as np
import pytest

from generic_grader.utils.octave_plot import SUPPORTED_PROPS, Points, get_property


class DummyTest(unittest.TestCase):
    """Concrete ``TestCase`` used as the ``test`` argument.

    Using a real ``TestCase`` (rather than a mock) means the failure
    text and exception type produced by :func:`get_property` match
    what a live plot test would see.
    """

    def runTest(self):  # pragma: no cover
        pass


@pytest.fixture()
def artifact():
    """Return a plot artifact shaped like the Octave harness JSON."""
    return {
        "figures": [
            {
                "axes": [
                    {
                        "title": "Simple plot",
                        "xlabel": "x-axis",
                        "ylabel": "y-axis",
                        "xlim": [1.0, 4.0],
                        "ylim": [0.0, 20.0],
                        "xticklabels": ["1", "2", "3", "4"],
                        "yticklabels": ["0", "10", "20"],
                        "lines": [
                            {
                                "xdata": [1.0, 2.0, 3.0, 4.0],
                                "ydata": [1.0, 4.0, 9.0, 16.0],
                                "color": [1.0, 0.0, 0.0],
                            },
                            {
                                "xdata": [0.0, 1.0],
                                "ydata": [2.0, 3.0],
                                "color": [0.0, 0.0, 1.0],
                            },
                        ],
                    }
                ]
            }
        ]
    }


@pytest.fixture()
def test_case():
    return DummyTest()


class TestScalarProperties:
    def test_title(self, artifact, test_case):
        assert get_property(test_case, artifact, "title", {}) == "Simple plot"

    def test_x_label(self, artifact, test_case):
        assert get_property(test_case, artifact, "x label", {}) == "x-axis"

    def test_y_label(self, artifact, test_case):
        assert get_property(test_case, artifact, "y label", {}) == "y-axis"

    def test_x_limits_becomes_tuple(self, artifact, test_case):
        assert get_property(test_case, artifact, "x limits", {}) == (1.0, 4.0)

    def test_y_limits_becomes_tuple(self, artifact, test_case):
        assert get_property(test_case, artifact, "y limits", {}) == (0.0, 20.0)

    def test_number_of_lines_counts_line_payloads(self, artifact, test_case):
        assert get_property(test_case, artifact, "number of lines", {}) == 2


class TestTickLabels:
    def test_x_tick_labels(self, artifact, test_case):
        assert get_property(test_case, artifact, "x tick labels", {}) == [
            "1",
            "2",
            "3",
            "4",
        ]

    def test_y_tick_labels(self, artifact, test_case):
        assert get_property(test_case, artifact, "y tick labels", {}) == [
            "0",
            "10",
            "20",
        ]


class TestLineData:
    def test_x_data_defaults_to_first_line(self, artifact, test_case):
        assert get_property(test_case, artifact, "x data", {}) == [
            1.0,
            2.0,
            3.0,
            4.0,
        ]

    def test_x_data_uses_index_kwarg(self, artifact, test_case):
        assert get_property(test_case, artifact, "x data", {"index": 1}) == [
            0.0,
            1.0,
        ]

    def test_y_data_defaults_to_first_line_rounded(self, artifact, test_case):
        assert get_property(test_case, artifact, "y data", {}) == [
            1.0,
            4.0,
            9.0,
            16.0,
        ]

    def test_y_data_uses_index_kwarg(self, artifact, test_case):
        assert get_property(test_case, artifact, "y data", {"index": 1}) == [
            2.0,
            3.0,
        ]

    def test_xy_data_returns_points_namedtuple(self, artifact, test_case):
        result = get_property(test_case, artifact, "xy data", {})
        assert isinstance(result, Points)
        assert np.array_equal(result.x, np.array([1.0, 2.0, 3.0, 4.0]))
        assert np.array_equal(result.y, np.array([1.0, 4.0, 9.0, 16.0]))

    def test_xy_data_uses_index_kwarg(self, artifact, test_case):
        result = get_property(test_case, artifact, "xy data", {"index": 1})
        assert np.array_equal(result.x, np.array([0.0, 1.0]))
        assert np.array_equal(result.y, np.array([2.0, 3.0]))


class TestLineColors:
    def test_named_colour_round_trips(self, artifact, test_case):
        colours = get_property(test_case, artifact, "line colors", {})
        # Matplotlib's colour dictionary is walked in sorted order and
        # the first named match wins, so a pure-red line resolves to
        # ``'r'`` (which precedes ``'red'``) and pure-blue to ``'b'``.
        assert colours == ["r", "b"]

    def test_falls_back_to_rgba_tuple(self, test_case):
        payload = {
            "figures": [
                {
                    "axes": [
                        {
                            "lines": [
                                {"color": [0.123, 0.456, 0.789]},
                            ]
                        }
                    ]
                }
            ]
        }
        colours = get_property(test_case, payload, "line colors", {})
        assert isinstance(colours[0], tuple)
        assert len(colours[0]) == 4


class TestErrorPaths:
    def test_missing_artifact_fails_with_hint(self, test_case):
        with pytest.raises(AssertionError) as exc:
            get_property(test_case, None, "title", {})
        assert "produces a plot" in str(exc.value)

    def test_empty_figures_fails_with_hint(self, test_case):
        with pytest.raises(AssertionError) as exc:
            get_property(test_case, {"figures": []}, "title", {})
        assert "produces a plot" in str(exc.value)

    def test_empty_axes_fails_with_hint(self, test_case):
        with pytest.raises(AssertionError) as exc:
            get_property(test_case, {"figures": [{"axes": []}]}, "title", {})
        assert "produces a plot" in str(exc.value)

    def test_out_of_range_line_index_fails(self, artifact, test_case):
        with pytest.raises(IndexError) as exc:
            get_property(test_case, artifact, "x data", {"index": 5})
        assert "Failed to find x data for data set 6" in str(exc.value)

    def test_unknown_property_raises_value_error(self, artifact, test_case):
        with pytest.raises(ValueError, match="not supported"):
            get_property(test_case, artifact, "bar widths", {})

    def test_none_kwargs_are_accepted(self, artifact, test_case):
        assert get_property(test_case, artifact, "title", None) == "Simple plot"


class TestSupportedProps:
    def test_supported_props_covers_all_dispatcher_branches(self, artifact, test_case):
        for prop in SUPPORTED_PROPS:
            # Round-tripping every prop shouldn't raise the
            # "not supported" ValueError.
            get_property(test_case, artifact, prop, {})
