"""Host-side facades that adapt serialized sandbox figures to matplotlib's API.

The sandbox worker can't ship live ``matplotlib.figure.Figure`` objects
across the IPC boundary, so it serializes them to JSON-safe dicts via
``sandbox.figure_serializer``.  The grader's plot helpers in
``generic_grader.utils.plot``, however, were written against the live
matplotlib API (``ax.get_lines()``, ``ax.containers``, ``ax.patches``,
``ax.spines``, etc.).

Rather than rewrite every ``get_*`` helper to branch on "serialized vs
live", we build thin facade objects here that quack like the axes /
line / bar / wedge / spine objects the plot helpers reach into.  The
plot helpers can then treat a sandbox-produced figure exactly like a
live one.

Only the surface that ``utils/plot.py`` actually touches is implemented
-- if a new plot helper reaches into a previously-unused matplotlib
attribute, this module will need a corresponding stub.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import matplotlib as mpl

# ---------------------------------------------------------------------------
# Small leaf facades
# ---------------------------------------------------------------------------


class _TextStub:
    """Stand-in for a matplotlib ``Text`` (title, tick label, legend entry)."""

    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self) -> str:
        return self._text


class _LineStub:
    """Stand-in for a matplotlib ``Line2D`` used by ``utils/plot.py``."""

    def __init__(self, line: dict[str, Any]) -> None:
        self._line = line

    def get_xdata(self) -> list[float]:
        return list(self._line.get("xdata", []))

    def get_ydata(self) -> list[float]:
        return list(self._line.get("ydata", []))

    def get_color(self) -> Any:
        name = self._line.get("color_name")
        if name is not None:
            return name
        rgba = self._line.get("color_rgba")
        if rgba is not None:
            return tuple(rgba)
        return (0.0, 0.0, 0.0, 1.0)


class _RectangleStub(mpl.patches.Rectangle):
    """A real Rectangle so ``isinstance(p, mpl.patches.Rectangle)`` works.

    The plot helpers (``get_number_bars``, ``get_x_data``, etc.) filter
    container patches with ``isinstance(patch, mpl.patches.Rectangle)``.
    We subclass the real Rectangle and let it carry the geometry we
    recorded in the serialized figure.
    """

    def __init__(self, x_center: float, width: float) -> None:
        # Use a unit-height rectangle; only x/width are read downstream.
        super().__init__((x_center - width / 2, 0.0), width, 1.0)


class _BarContainerStub(mpl.container.BarContainer):
    """A real BarContainer so ``isinstance(..., BarContainer)`` works."""

    def __init__(self, bars: Sequence[dict[str, Any]], values: Sequence[float]) -> None:
        patches = [_RectangleStub(b["x_center"], b["width"]) for b in bars]
        super().__init__(patches, datavalues=tuple(values))


class _WedgeStub(mpl.patches.Wedge):
    """A real Wedge so ``isinstance(p, mpl.patches.Wedge)`` works.

    ``utils/plot.py:get_pie_wedges`` filters axes patches with
    ``isinstance(p, mpl.patches.Wedge)``, then asks for ``get_label``,
    ``get_facecolor``, ``theta1``/``theta2``.  We hand-build a real
    Wedge with the recorded label, color, and angle.
    """

    def __init__(self, wedge: dict[str, Any]) -> None:
        # A unit-radius wedge centered at the origin; angles encode the
        # serialized ``angle_degrees`` (theta2 - theta1).
        super().__init__(
            center=(0.0, 0.0),
            r=1.0,
            theta1=0.0,
            theta2=float(wedge.get("angle_degrees", 0.0)),
        )
        self.set_label(wedge.get("label", ""))
        # Drop alpha to match how to_hex round-trips.
        self.set_facecolor(wedge.get("color_hex", "#000000"))


class _GridLineStub:
    """Stand-in for a gridline that exposes ``get_path().vertices``."""

    class _Path:
        def __init__(self, vertices: Sequence[Sequence[float]]) -> None:
            self.vertices = [tuple(v) for v in vertices]

    def __init__(self, vertices: Sequence[Sequence[float]]) -> None:
        self._path = self._Path(vertices)

    def get_visible(self) -> bool:
        # All gridlines in the serialized dict were already filtered to
        # the visible set by the worker, so we always return True here.
        return True

    def get_path(self) -> "_GridLineStub._Path":
        return self._path


class _AxisStub:
    """Stand-in for ``ax.get_xaxis()`` / ``ax.get_yaxis()`` -- only
    ``get_gridlines()`` is exercised by the plot helpers."""

    def __init__(self, gridlines: Sequence[_GridLineStub]) -> None:
        self._gridlines = list(gridlines)

    def get_gridlines(self) -> list[_GridLineStub]:
        return list(self._gridlines)


class _SpineStub:
    """Stand-in for a matplotlib ``Spine``."""

    def __init__(self, visible: bool, position: Any) -> None:
        # Encode visibility as ``visible flag * linewidth * alpha`` --
        # the plot helper multiplies all three together, so setting
        # the latter two to 1 when visible reproduces the live result.
        self._visible = bool(visible)
        self._position = position

    def get_visible(self) -> bool:
        return self._visible

    def get_linewidth(self) -> float:
        return 1.0 if self._visible else 0.0

    def get_edgecolor(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, 0.0, 1.0 if self._visible else 0.0)

    def get_position(self) -> Any:
        if isinstance(self._position, list):
            return (self._position[0], self._position[1])
        return self._position


class _LegendStub:
    """Stand-in for ``ax.get_legend()``; just needs ``.texts``."""

    def __init__(self, labels: Sequence[str]) -> None:
        self.texts = [_TextStub(label) for label in labels]


# ---------------------------------------------------------------------------
# Axes / Figure
# ---------------------------------------------------------------------------


class SerializedAxes:
    """Facade that adapts one serialized axes dict to matplotlib's API.

    Only the surface used by ``generic_grader.utils.plot`` is exposed.
    The facade is read-only -- it does not mutate the underlying dict.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        # Lazily-built collections so repeated calls hand back the same
        # stubs (matches matplotlib's behavior of returning identity-
        # stable handles within a draw cycle).
        self._lines: list[_LineStub] | None = None
        self._containers: list[_BarContainerStub] | None = None
        self._patches: list[Any] | None = None
        self._spines: dict[str, _SpineStub] | None = None
        self._title_text: _TextStub = _TextStub(data.get("title", ""))

    # --- Title / labels -------------------------------------------------
    @property
    def title(self) -> _TextStub:
        return self._title_text

    def get_xlabel(self) -> str:
        return self._data.get("xlabel", "")

    def get_ylabel(self) -> str:
        return self._data.get("ylabel", "")

    # --- Limits ---------------------------------------------------------
    def get_xlim(self) -> tuple[float, float]:
        x0, x1 = self._data.get("xlim", [0.0, 1.0])
        return (float(x0), float(x1))

    def get_ylim(self) -> tuple[float, float]:
        y0, y1 = self._data.get("ylim", [0.0, 1.0])
        return (float(y0), float(y1))

    # --- Tick labels ----------------------------------------------------
    def get_xticklabels(self) -> list[_TextStub]:
        return [_TextStub(t) for t in self._data.get("xticklabels", [])]

    def get_yticklabels(self) -> list[_TextStub]:
        return [_TextStub(t) for t in self._data.get("yticklabels", [])]

    # --- Lines / containers / patches -----------------------------------
    def get_lines(self) -> list[_LineStub]:
        if self._lines is None:
            self._lines = [_LineStub(line) for line in self._data.get("lines", [])]
        return list(self._lines)

    @property
    def containers(self) -> list[_BarContainerStub]:
        if self._containers is None:
            bars = self._data.get("bars", []) or []
            values = self._data.get("bar_values", []) or []
            if bars:
                self._containers = [_BarContainerStub(bars, values)]
            else:
                self._containers = []
        return list(self._containers)

    @property
    def patches(self) -> list[Any]:
        if self._patches is None:
            self._patches = [_WedgeStub(w) for w in self._data.get("wedges", [])]
        return list(self._patches)

    # --- Axis / gridlines ----------------------------------------------
    def get_xaxis(self) -> _AxisStub:
        return _AxisStub(self._x_gridlines())

    def get_yaxis(self) -> _AxisStub:
        return _AxisStub(self._y_gridlines())

    def _x_gridlines(self) -> list[_GridLineStub]:
        # The serialized format keeps x-axis (vertical) and y-axis
        # (horizontal) gridlines in separate fields so we can hand
        # ``ax.get_xaxis().get_gridlines()`` exactly the set that the
        # live matplotlib path would return.  Without this split,
        # ``utils.plot.get_grid_lines`` double-counts gridlines
        # whenever ``xlim`` and ``ylim`` overlap (e.g. both ranges
        # include 0), because each gridline's first vertex then
        # satisfies both the x and y window filters.
        raw = self._data.get("x_grid_lines")
        if raw is None:
            # Backwards compatibility for figures serialized under the
            # original ``grid_lines`` schema -- hand both axes the full
            # list and accept the double-count.  Layer-3 always writes
            # the new fields, so this path is exercised by legacy fixtures only.
            raw = self._data.get("grid_lines", [])
        return [_GridLineStub(v) for v in raw]

    def _y_gridlines(self) -> list[_GridLineStub]:
        raw = self._data.get("y_grid_lines")
        if raw is None:
            raw = self._data.get("grid_lines", [])
        return [_GridLineStub(v) for v in raw]

    # --- Spines / legend -----------------------------------------------
    @property
    def spines(self) -> dict[str, _SpineStub]:
        if self._spines is None:
            visibility = self._data.get("spine_visibility", {}) or {}
            positions = self._data.get("spine_positions", {}) or {}
            self._spines = {
                name: _SpineStub(visibility.get(name, False), positions.get(name))
                for name in visibility
            }
        return dict(self._spines)

    def get_legend(self) -> _LegendStub | None:
        labels = self._data.get("legend")
        if labels is None:
            return None
        return _LegendStub(labels)


class SerializedFigure:
    """Facade for a whole serialized figure (a list of axes dicts)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get_axes(self) -> list[SerializedAxes]:
        return [SerializedAxes(ax) for ax in self._data.get("axes", [])]


__all__ = (
    "SerializedFigure",
    "SerializedAxes",
)
