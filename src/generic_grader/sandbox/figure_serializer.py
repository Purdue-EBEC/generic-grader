"""Serialize a matplotlib Figure to a JSON-safe dict.

The grader's existing plot tests reach into a live `plt.gcf()` to
extract every property they care about (title, axes, line xdata/ydata,
colors, bar widths, pie wedges, legend, grid lines, spine state,
etc.). Those calls live in `generic_grader/utils/plot.py`.

Once Layer 3 lands, the student's code runs in a separate sandboxed
process. We cannot ship a `Figure` over a pipe; we ship a dict
instead.  This module is responsible for producing that dict from
inside the sandbox worker. The companion change in commit 6 will
rewrite `utils/plot.py` to read from the same dict on the host side,
so the surface area the grader code uses is unchanged.

Schema (version 1):

    {
        "format":  "matplotlib-figure",
        "version": 1,
        "axes": [
            {
                "title":            str,
                "xlabel":           str,
                "ylabel":           str,
                "xlim":             [float, float],
                "ylim":             [float, float],
                "xticklabels":      [str, ...],
                "yticklabels":      [str, ...],
                "legend":           [str, ...] | None,
                "lines": [
                    {
                        "xdata":      [float, ...],
                        "ydata":      [float, ...],
                        "color_name": str | None,
                        "color_rgba": [float, float, float, float] | None,
                    },
                    ...
                ],
                "bars": [
                    {"x_center": float, "width": float},
                    ...
                ],
                "bar_values":       [float, ...],
                "wedges": [
                    {
                        "label":         str,
                        "color_hex":     str,
                        "angle_degrees": float,
                    },
                    ...
                ],
                "grid_lines": [[[float, float], ...], ...],
                "spine_visibility":  {name: bool, ...},
                "spine_positions":   {name: [kind, value] | "zero" | "center", ...},
            },
            ...
        ]
    }

All numerical values are plain Python ``float`` / ``int`` -- never
numpy scalars -- so the dict round-trips cleanly through ``json``.
"""

from __future__ import annotations

from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

FORMAT_VERSION = 1


# ---------------------------------------------------------------------------
# Scalar coercion
# ---------------------------------------------------------------------------


def _as_float(value: Any) -> float:
    """Coerce numpy scalars / Python numbers to a plain ``float``."""
    return float(value)


def _as_float_list(values: Any) -> list[float]:
    """Convert an iterable (incl. ndarray / MaskedArray) into a list of floats.

    matplotlib stores ``xdata`` as raw ``datetime.date`` / ``datetime.datetime``
    objects when the student calls ``plot(dates, ...)``. We coerce those
    through ``date2num`` so the wire format is uniformly floats and the
    host can re-hydrate dates with ``mpl.dates.num2date`` exactly like
    the existing ``utils/plot.py:get_x_time_data`` does.
    """
    arr = np.asarray(values)
    if arr.dtype == object:
        # Likely a date array; convert via matplotlib's date helpers.
        try:
            arr = mpl.dates.date2num(arr)
        except (TypeError, ValueError, AttributeError):
            # Fall back to coercing element-by-element; anything that
            # doesn't survive ``float()`` becomes a NaN.
            out: list[float] = []
            for v in arr.tolist():
                try:
                    out.append(float(v))
                except (TypeError, ValueError):
                    out.append(float("nan"))
            return out
    return [float(v) for v in np.asarray(arr, dtype=float).tolist()]


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------


# Computed once so each line lookup is a linear scan over a sorted list,
# matching plot.get_line_colors exactly.
_NAMED_COLORS = sorted(mpl.colors.get_named_colors_mapping().items())


def _named_or_rgba(color: Any) -> tuple[str | None, list[float] | None]:
    """Return ``(name, None)`` if a named color matches, else ``(None, rgba)``."""
    for name, candidate in _NAMED_COLORS:
        if mpl.colors.same_color(candidate, color):
            return name, None
    rgba = mpl.colors.to_rgba(color)
    return None, [float(c) for c in rgba]


# ---------------------------------------------------------------------------
# Per-feature extractors
# ---------------------------------------------------------------------------


def _serialize_lines(ax) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for line in ax.get_lines():
        name, rgba = _named_or_rgba(line.get_color())
        lines.append(
            {
                "xdata": _as_float_list(line.get_xdata()),
                "ydata": [round(v, 6) for v in _as_float_list(line.get_ydata())],
                "color_name": name,
                "color_rgba": rgba,
            }
        )
    return lines


def _serialize_bars(ax) -> tuple[list[dict[str, Any]], list[float]]:
    """Return ``(bars, datavalues)`` matching plot.get_x_data / get_y_data."""
    containers = ax.containers
    if not containers or not isinstance(containers[0], mpl.container.BarContainer):
        return [], []
    container = containers[0]
    bars: list[dict[str, Any]] = []
    for patch in container.patches:
        if not isinstance(patch, mpl.patches.Rectangle):
            continue
        width = _as_float(patch.get_width())
        x_center = _as_float(patch.get_x()) + width / 2
        bars.append({"x_center": x_center, "width": width})
    values = [round(_as_float(v), 6) for v in container.datavalues]
    return bars, values


def _serialize_wedges(ax) -> list[dict[str, Any]]:
    wedges: list[dict[str, Any]] = []
    for patch in ax.patches:
        if not isinstance(patch, mpl.patches.Wedge):
            continue
        wedges.append(
            {
                "label": patch.get_label(),
                "color_hex": mpl.colors.to_hex(patch.get_facecolor()),
                "angle_degrees": round(
                    _as_float(patch.theta2) - _as_float(patch.theta1), 4
                ),
            }
        )
    return wedges


def _serialize_tick_labels(getter) -> list[str]:
    return [label.get_text() for label in getter()]


def _serialize_grid_lines(ax) -> list[list[list[float]]]:
    """Return the visible grid lines filtered to the axes window."""
    x_gridlines = ax.get_xaxis().get_gridlines()
    y_gridlines = ax.get_yaxis().get_gridlines()
    visible_x = [g for g in x_gridlines if g.get_visible()]
    visible_y = [g for g in y_gridlines if g.get_visible()]
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()

    def to_vertices(line):
        return [[float(p[0]), float(p[1])] for p in line.get_path().vertices]

    lines: list[list[list[float]]] = []
    for g in visible_x:
        vs = to_vertices(g)
        if vs and xmin <= vs[0][0] <= xmax:
            lines.append(vs)
    for g in visible_y:
        vs = to_vertices(g)
        if vs and ymin <= vs[0][1] <= ymax:
            lines.append(vs)
    return lines


def _serialize_spine_visibility(ax) -> dict[str, bool]:
    visibility: dict[str, bool] = {}
    for name, spine in ax.spines.items():
        visible = spine.get_visible()
        linewidth = spine.get_linewidth()
        alpha_channel = spine.get_edgecolor()[3]
        visibility[name] = bool(visible and linewidth and alpha_channel)
    return visibility


def _serialize_spine_positions(ax) -> dict[str, Any]:
    """Return spine positions as JSON-safe tuples or strings.

    Matplotlib stores spine positions either as a 2-tuple ``(kind,
    amount)`` (e.g. ``('data', 0.5)``) or as one of the bare-string
    shortcuts (``'zero'``, ``'center'``). We preserve both forms.
    """
    positions: dict[str, Any] = {}
    for name, spine in ax.spines.items():
        pos = spine.get_position()
        if isinstance(pos, str):
            positions[name] = pos
        else:
            kind, value = pos
            positions[name] = [kind, _as_float(value)]
    return positions


def _serialize_legend(ax) -> list[str] | None:
    legend = ax.get_legend()
    return [t.get_text() for t in legend.texts] if legend else None


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def _serialize_axes(ax) -> dict[str, Any]:
    bars, bar_values = _serialize_bars(ax)
    return {
        "title": ax.title.get_text(),
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "xlim": [_as_float(v) for v in ax.get_xlim()],
        "ylim": [_as_float(v) for v in ax.get_ylim()],
        "xticklabels": _serialize_tick_labels(ax.get_xticklabels),
        "yticklabels": _serialize_tick_labels(ax.get_yticklabels),
        "lines": _serialize_lines(ax),
        "bars": bars,
        "bar_values": bar_values,
        "wedges": _serialize_wedges(ax),
        "legend": _serialize_legend(ax),
        "grid_lines": _serialize_grid_lines(ax),
        "spine_visibility": _serialize_spine_visibility(ax),
        "spine_positions": _serialize_spine_positions(ax),
    }


def serialize_figure(fig) -> dict[str, Any]:
    """Serialize a matplotlib ``Figure`` to a JSON-safe dict.

    The caller (the sandbox worker) is responsible for invoking this
    before closing the figure.  Tick labels require a draw to be
    populated, so the function forces ``canvas.draw()`` first --
    exactly like the existing ``get_x_tick_labels`` and friends in
    ``utils/plot.py``.
    """
    try:
        fig.canvas.draw()
    except Exception:  # pragma: no cover - draw failure is best-effort
        pass

    axes_data = [_serialize_axes(ax) for ax in fig.get_axes()]
    return {
        "format": "matplotlib-figure",
        "version": FORMAT_VERSION,
        "axes": axes_data,
    }


def serialize_current_figures() -> list[dict[str, Any]]:
    """Serialize every open pyplot figure, then close them all.

    Returns a list (possibly empty) of serialized figure dicts in the
    order matplotlib reports them. After this call ``plt.get_fignums()``
    is empty, so a subsequent worker run starts clean.
    """
    serialized: list[dict[str, Any]] = []
    for num in plt.get_fignums():
        fig = plt.figure(num)
        serialized.append(serialize_figure(fig))
    plt.close("all")
    return serialized


__all__ = ("serialize_figure", "serialize_current_figures", "FORMAT_VERSION")
