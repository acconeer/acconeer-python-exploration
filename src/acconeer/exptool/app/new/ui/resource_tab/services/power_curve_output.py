# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import itertools
import operator
import typing as t

import attrs
import typing_extensions as te

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsSceneMouseEvent,
    QGridLayout,
    QTabWidget,
    QToolTip,
    QWidget,
)

import pyqtgraph as pg

from acconeer.exptool import a2, a121
from acconeer.exptool.a2.model import power as a2_power
from acconeer.exptool.a2.model.power.formatting import _collect_components, format_energy
from acconeer.exptool.a121.model import power as a121_power
from acconeer.exptool.app.new.ui.icons import WARNING_YELLOW
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    BreakdownToggleEvent,
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)

from ._a2_power_selections import APS_ACTIVE_STATE
from .a2_heatmap_capon_config_input import HeatmapCaponConfigEvent
from .a2_heatmap_coherent_config_input import HeatmapCoherentConfigEvent
from .a2_heatmap_conventional_config_input import HeatmapConventionalConfigEvent
from .a2_heatmap_robust_capon_config_input import HeatmapRobustCaponConfigEvent
from .a2_session_config_input import SessionConfigEvent as A2SessionConfigEvent
from .a121_session_config_input import SessionConfigEvent as A121SessionConfigEvent
from .distance_config_input import DistanceConfigEvent
from .presence_config_input import PresenceConfigEvent


_SECONDS_IF_RATE_UNSET = 2e-2
_DURATION_SB_DECIMALS = 4
_DURATION_SB_RANGE = (1e-4, 100)
_DURATION_SB_STEP = 5e-3

_X_AXIS_SPINBOX_LABEL = "X-axis length"
_MU = "\u00b5"

_A_to_mA = _s_to_ms = _mA_to_uA = 1000
_A_to_uA = _s_to_us = 1000000

_mA = _ms = 1e-3


class PowerCurveBarGraphItem(pg.BarGraphItem):
    def __init__(
        self,
        power_profile: a121_power.CompositeRegion | a2_power.CompositeRegion,
    ) -> None:
        durations = [r.duration for r in power_profile.flat_iter()]
        starts = list(itertools.accumulate([0] + durations[:-1], operator.add))
        currents = [p.average_current for p in power_profile.flat_iter()]
        colors = [self.tag_color(p.tag) for p in power_profile.flat_iter()]

        super().__init__(
            x0=starts,
            width=durations,
            height=currents,
            brushes=colors,
        )
        self.setAcceptHoverEvents(True)

        self._power_profile = power_profile
        self._ends = [start + duration for start, duration in zip(starts, durations)]

        regions: list[t.Any] = list(power_profile.flat_iter())
        total_energy = sum(r.average_current * r.duration for r in regions)
        energy_by_tag: dict[t.Any, float] = {}
        energy_by_desc: dict[str, float] = {}
        for r in regions:
            energy_by_tag[r.tag] = energy_by_tag.get(r.tag, 0.0) + r.average_current * r.duration
            energy_by_desc[r.description] = (
                energy_by_desc.get(r.description, 0.0) + r.average_current * r.duration
            )
        self._total_energy = total_energy
        self._energy_share_by_tag = {
            tag: e / total_energy if total_energy > 0 else 0.0 for tag, e in energy_by_tag.items()
        }
        self._energy_share_by_desc = {
            desc: e / total_energy if total_energy > 0 else 0.0
            for desc, e in energy_by_desc.items()
        }

    @staticmethod
    def tag_color(
        tag: a121_power.EnergyRegion.Tag | a2_power.EnergyRegion.Tag | None,
    ) -> str:
        if tag in [a121_power.EnergyRegion.Tag.MEASURE, a2_power.EnergyRegion.Tag.MEASURE]:
            return "cornflowerblue"
        if tag in [a121_power.EnergyRegion.Tag.OVERHEAD, a2_power.EnergyRegion.Tag.OVERHEAD]:
            return "red"
        if tag in [a121_power.EnergyRegion.Tag.CALIBRATION, a2_power.EnergyRegion.Tag.CALIBRATION]:
            return "orange"
        if tag in [a121_power.EnergyRegion.Tag.IDLE, a2_power.EnergyRegion.Tag.IDLE]:
            return "forestgreen"
        if tag == a121_power.EnergyRegion.Tag.COMMUNICATION:
            return "goldenrod"
        if tag == a2_power.EnergyRegion.Tag.RS_INITIALIZATION:
            return "darkcyan"
        if tag == a2_power.EnergyRegion.Tag.APS_INITIALIZATION:
            return "yellow"

        return "magenta"

    def _profile_description_at_point(self, x: float, y: float) -> str:
        simple_profile: t.Any
        for end, simple_profile in zip(self._ends, self._power_profile.flat_iter()):
            if x >= end:
                continue

            if y < simple_profile.average_current:
                avg = simple_profile.average_current
                if avg > 1.0:
                    approx_current_formatted = f"{avg:.1f} A"
                elif avg > 1.0e-3:
                    approx_current_formatted = f"{avg * _A_to_mA:.1f} mA"
                else:
                    approx_current_formatted = f"{avg * _A_to_uA:.0f} {_MU}A"

                if simple_profile.duration > 1.0:
                    approx_duration_formatted = f"{simple_profile.duration:.1f} s"
                elif simple_profile.duration > 1.0e-3:
                    approx_duration_formatted = f"{simple_profile.duration * _s_to_ms:.1f} ms"
                else:
                    approx_duration_formatted = f"{simple_profile.duration * _s_to_us:.0f} {_MU}s"
                tag_name = simple_profile.tag.name.title() if simple_profile.tag else "Unknown"
                return "\n".join(
                    [
                        simple_profile.description,
                        "",
                        f"Current: {approx_current_formatted}",
                        f"Duration: {approx_duration_formatted}",
                        f"Energy: {format_energy(simple_profile.average_current, simple_profile.duration)}",
                        f"Energy share ({simple_profile.description}):"
                        f" {self._energy_share_by_desc.get(simple_profile.description, 0.0) * 100:.1f}%",
                        f"Energy share ({tag_name}):"
                        f" {self._energy_share_by_tag.get(simple_profile.tag, 0.0) * 100:.1f}%",
                    ]
                )
            else:
                return ""

        return ""

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        x = event.pos().x()
        y = event.pos().y()
        global_pos = event.screenPos()
        tooltip = self._profile_description_at_point(x, y)

        if tooltip:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(tooltip)

        # Work-around to be able to get tooltip-on-click and zoom with rectangle
        QTimer.singleShot(10, lambda: QToolTip.showText(global_pos, tooltip))
        super().mousePressEvent(event)

    def hoverEvent(self, event: t.Any) -> None:
        try:
            x = event.pos().x()
            y = event.pos().y()
        except Exception:
            return

        tooltip = self._profile_description_at_point(x, y)
        self.setToolTip(tooltip)


_TILE_SIZE = 10
_PATTERN_COLOR = QColor(0, 0, 0, 120)


def _draw_pattern(painter: QPainter, idx: int, sz: int) -> None:
    """Draw a distinguishing pattern onto an sz x sz tile."""
    pen = QPen(_PATTERN_COLOR, 2)
    painter.setPen(pen)
    if idx == 0:
        pass  # solid — no overlay
    elif idx == 1:
        # horizontal lines
        for y in range(0, sz, 4):
            painter.drawLine(0, y, sz, y)
    elif idx == 2:
        # vertical lines
        for x in range(0, sz, 4):
            painter.drawLine(x, 0, x, sz)
    elif idx == 3:
        # forward diagonal
        for d in range(-sz, 2 * sz, 5):
            painter.drawLine(d, 0, d + sz, sz)
    elif idx == 4:
        # back diagonal
        for d in range(-sz, 2 * sz, 5):
            painter.drawLine(d + sz, 0, d, sz)
    elif idx == 5:
        # cross-hatch
        for y in range(0, sz, 5):
            painter.drawLine(0, y, sz, y)
        for x in range(0, sz, 5):
            painter.drawLine(x, 0, x, sz)
    elif idx == 6:
        # diagonal cross
        for d in range(-sz, 2 * sz, 5):
            painter.drawLine(d, 0, d + sz, sz)
            painter.drawLine(d + sz, 0, d, sz)
    else:
        # dots
        pen.setWidth(3)
        painter.setPen(pen)
        for y in range(2, sz, 5):
            for x in range(2, sz, 5):
                painter.drawPoint(x, y)


def _make_component_tile(color: QColor, component_index: int) -> QPixmap:
    """Create a small tile filled with *color* and a distinguishing overlay."""
    pixmap = QPixmap(_TILE_SIZE, _TILE_SIZE)
    pixmap.fill(color)
    painter = QPainter(pixmap)
    _draw_pattern(painter, component_index % 8, _TILE_SIZE)
    painter.end()
    return pixmap


def _component_brush(
    tag: a2_power.EnergyRegion.Tag | None,
    component_index: int,
) -> QBrush:
    """Return a patterned brush for a component layer using the tag's base color."""
    color = QColor(PowerCurveBarGraphItem.tag_color(tag))
    return QBrush(_make_component_tile(color, component_index))


class _TexturedBarLayer(pg.GraphicsObject):
    """Draws bars with textured brushes in pixel coordinates.

    Standard BarGraphItem transforms the brush texture through data
    coordinates, squishing patterns to sub-pixel size.  This item maps
    data rectangles to pixel space before drawing so the texture tiles
    remain at their native resolution.
    """

    _LABEL_FONT = QFont("sans-serif", 8)
    _LABEL_BG = QColor(255, 255, 255, 180)
    _MIN_LABEL_HEIGHT = 12
    _MIN_LABEL_WIDTH = 18

    def __init__(
        self,
        x0: list[float],
        widths: list[float],
        y0: list[float],
        heights: list[float],
        brushes: list[QBrush],
        label: str = "",
    ) -> None:
        super().__init__()
        self._x0 = x0
        self._widths = widths
        self._y0 = y0
        self._heights = heights
        self._brushes = brushes
        self._label = label

    def paint(self, painter: QPainter, option: t.Any, widget: t.Any) -> None:
        transform = painter.transform()
        painter.resetTransform()
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        label_rects: list[QRectF] = []
        for x0, w, y0, h, brush in zip(
            self._x0, self._widths, self._y0, self._heights, self._brushes
        ):
            top_left = transform.map(QPointF(x0, y0 + h))
            bottom_right = transform.map(QPointF(x0 + w, y0))
            rect = QRectF(top_left, bottom_right).normalized()
            painter.setBrush(brush)
            painter.drawRect(rect)
            label_rects.append(rect)

        if self._label:
            painter.setFont(self._LABEL_FONT)
            fm = QFontMetrics(self._LABEL_FONT)
            text_width = fm.horizontalAdvance(self._label)
            text_height = fm.height()
            pad = 1
            for rect in label_rects:
                if (
                    rect.height() >= self._MIN_LABEL_HEIGHT
                    and rect.width() >= self._MIN_LABEL_WIDTH
                ):
                    bg_rect = QRectF(
                        rect.x() + pad,
                        rect.y() + pad,
                        text_width + 4,
                        text_height + 2,
                    )
                    painter.setPen(QPen(Qt.PenStyle.NoPen))
                    painter.setBrush(QBrush(self._LABEL_BG))
                    painter.drawRect(bg_rect)
                    painter.setPen(QPen(QColor(0, 0, 0, 200)))
                    painter.drawText(
                        bg_rect,
                        Qt.AlignmentFlag.AlignCenter,
                        self._label,
                    )

        painter.setTransform(transform)

    def boundingRect(self) -> QRectF:
        if not self._x0:
            return QRectF()
        x_min = min(self._x0)
        x_max = max(x0 + w for x0, w in zip(self._x0, self._widths))
        y_min = min(self._y0)
        y_max = max(y0 + h for y0, h in zip(self._y0, self._heights))
        return QRectF(x_min, y_min, x_max - x_min, y_max - y_min)


class StackedBreakdownBarGroup:
    """Renders stacked per-component bars for an A2 CompositeRegion.

    Each component layer uses the tag's base color with a distinct fill pattern
    (solid, dense, diagonal, horizontal, cross) to differentiate components.
    """

    def __init__(self, power_profile: a2_power.CompositeRegion) -> None:
        regions = list(power_profile.flat_iter())
        durations = [r.duration for r in regions]
        starts = list(itertools.accumulate([0.0] + durations[:-1], operator.add))
        # Component order comes from the profile data itself, not a hardcoded
        # enum, so the same widget renders whichever components the YAML
        # provided.
        components = _collect_components(power_profile)

        self._component_order: tuple[str, ...] = components
        self._bar_items: list[_TexturedBarLayer] = []

        # Stack bottom-to-top in reverse sort order so the alphabetically
        # first component ends up at the top of the bar.
        stacking_order = list(reversed(components))

        for stack_idx, component in enumerate(stacking_order):
            orig_idx = components.index(component)
            y0_list: list[float] = []
            heights: list[float] = []
            brushes: list[QBrush] = []

            for region in regions:
                if isinstance(region.current, a2_power.CurrentBreakdown):
                    bd = region.current
                    base = sum(bd.currents.get(s, 0.0) for s in stacking_order[:stack_idx])
                    y0_list.append(base)
                    heights.append(bd.currents.get(component, 0.0))
                else:
                    y0_list.append(0.0)
                    heights.append(0.0)
                brushes.append(_component_brush(region.tag, orig_idx))

            item = _TexturedBarLayer(
                x0=starts,
                widths=durations,
                y0=y0_list,
                heights=heights,
                brushes=brushes,
                label=component,
            )
            self._bar_items.append(item)

        # Transparent overlay for hover/click tooltips
        full_heights = [r.average_current for r in regions]
        self._overlay = pg.BarGraphItem(
            x0=starts,
            width=durations,
            height=full_heights,
            brush=pg.mkBrush(0, 0, 0, 0),
            pen=pg.mkPen(None),
        )
        self._overlay.setAcceptHoverEvents(True)

        self._ends = [s + d for s, d in zip(starts, durations)]
        self._regions = regions
        self._total_energy = sum(r.average_current * r.duration for r in regions)
        energy_by_tag: dict[t.Any, float] = {}
        for r in regions:
            energy_by_tag[r.tag] = energy_by_tag.get(r.tag, 0.0) + r.average_current * r.duration
        self._energy_share_by_tag = {
            tag: e / self._total_energy if self._total_energy > 0 else 0.0
            for tag, e in energy_by_tag.items()
        }
        energy_by_desc: dict[str, float] = {}
        for r in regions:
            energy_by_desc[r.description] = (
                energy_by_desc.get(r.description, 0.0) + r.average_current * r.duration
            )
        self._energy_share_by_desc = {
            desc: e / self._total_energy if self._total_energy > 0 else 0.0
            for desc, e in energy_by_desc.items()
        }

        self._overlay.hoverEvent = self._hover_event
        self._overlay.mousePressEvent = self._mouse_press_event

    def add_to_plot(self, plot_widget: pg.PlotWidget) -> None:
        for item in self._bar_items:
            plot_widget.addItem(item)
        plot_widget.addItem(self._overlay)

    def _format_current(self, current: float) -> str:
        if current > 1.0:
            return f"{current:.1f} A"
        elif current > 1.0e-3:
            return f"{current * _A_to_mA:.1f} mA"
        else:
            return f"{current * _A_to_uA:.0f} {_MU}A"

    def _format_duration(self, dur: float) -> str:
        if dur > 1.0:
            return f"{dur:.1f} s"
        elif dur > 1.0e-3:
            return f"{dur * _s_to_ms:.1f} ms"
        else:
            return f"{dur * _s_to_us:.0f} {_MU}s"

    def _tooltip_at(self, x: float, y: float) -> str:
        for end, region in zip(self._ends, self._regions):
            if x >= end:
                continue
            if y >= region.average_current:
                return ""

            lines = [
                region.description,
                "",
                f"Total: {self._format_current(region.average_current)}",
                f"Duration: {self._format_duration(region.duration)}",
                f"Energy: {format_energy(region.average_current, region.duration)}",
                f"Energy share ({region.description}):"
                f" {self._energy_share_by_desc.get(region.description, 0.0) * 100:.1f}%",
                f"Energy share ({region.tag.name.title() if region.tag else 'Unknown'}):"
                f" {self._energy_share_by_tag.get(region.tag, 0.0) * 100:.1f}%",
            ]
            if isinstance(region.current, a2_power.CurrentBreakdown):
                bd = region.current
                lines.append("")
                for component in self._component_order:
                    c = bd.currents.get(component, 0.0)
                    if c > 0:
                        lines.append(f"  {component}: {self._format_current(c)}")
            return "\n".join(lines)
        return ""

    def _hover_event(self, event: t.Any) -> None:
        try:
            x = event.pos().x()
            y = event.pos().y()
        except Exception:
            return
        self._overlay.setToolTip(self._tooltip_at(x, y))

    def _mouse_press_event(self, event: QGraphicsSceneMouseEvent) -> None:
        x = event.pos().x()
        y = event.pos().y()
        global_pos = event.screenPos()
        tooltip = self._tooltip_at(x, y)

        if tooltip:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(tooltip)

        # Work-around to be able to get tooltip-on-click and zoom with rectangle
        QTimer.singleShot(10, lambda: QToolTip.showText(global_pos, tooltip))
        # Propagate so pyqtgraph can handle panning
        pg.BarGraphItem.mousePressEvent(self._overlay, event)


class _DummyBarGraphItem(pg.BarGraphItem):
    def __init__(self, color: str) -> None:
        super().__init__(brush=color, x0=1, width=1, y0=1, height=1)


class _DummyPatternBarGraphItem(pg.BarGraphItem):
    def __init__(self, brush: QBrush) -> None:
        super().__init__(brush=brush, x0=1, width=1, y0=1, height=1)


class PowerCurvePlotItem(pg.PlotItem):
    """
    Just like pg.PlotItem, but the 'auto' range
    (which is applied when clicking the "A" button) is customizable in X-axis.
    """

    def __init__(self, *args: t.Any, auto_end_x: float, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._auto_end_x: float = auto_end_x

    def set_auto_end_x(self, x: float) -> None:
        self._auto_end_x = x

    def autoBtnClicked(self) -> None:
        if self.autoBtn.mode == "auto":
            # default behaviour is self.enableAutoRange()
            self.setXRange(0, self._auto_end_x)
            self.autoBtn.hide()
        else:
            self.disableAutoRange()


class _A121EnergyRegionPlot(QWidget):
    @attrs.frozen
    class _State:
        """Whenever this changes, the plot is redrawn (with the new information)"""

        session_config: a121.SessionConfig
        """This received from events"""

        lower_idle_state: a121_power.Sensor.LowerIdleState | None

    _MIN_DURATION_S = 20 * _ms
    _MAX_DURATION_S = 10

    def __init__(
        self,
        session_config: a121.SessionConfig,
        lower_idle_state: a121_power.Sensor.LowerIdleState | None,
        algorithm: a121_power.algo.Algorithm,
    ) -> None:
        super().__init__()

        self._state = self._State(session_config, lower_idle_state)
        self._algorithm: te.Final[a121_power.algo.Algorithm] = algorithm

        duration_of_2_actives = a121_power.session(
            session_config,
            lower_idle_state=lower_idle_state,
            num_actives=2,
            algorithm=algorithm,
        ).duration
        self._plot_item = PowerCurvePlotItem(auto_end_x=duration_of_2_actives)
        self._plot_item.autoBtnClicked()

        self._plot_item.setLabel("left", "Sensor + XM125", units="A")
        self._plot_item.setLabel("bottom", "Duration", units="s")
        self._plot_item.setContentsMargins(0, 0, 0, 10)

        self._plot_widget = pg.PlotWidget(plotItem=self._plot_item)
        self._plot_widget.getViewBox().setMouseMode(pg.ViewBox.PanMode)
        y_min = -0.01
        y_max = 0.1
        self._plot_widget.getViewBox().setLimits(
            yMin=y_min, yMax=y_max, minYRange=y_max - y_min, maxYRange=y_max - y_min
        )

        self._bar_legend = pg.graphicsItems.LegendItem.LegendItem(offset=(75, 10))
        self._bar_legend.setParentItem(self._plot_item)
        self._bar_legend.setEnabled(False)

        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot_widget, 0, 0, 1, 2)
        self.setLayout(layout)

    def evolve_current_state(self, **kwargs: t.Any) -> None:
        self._state = attrs.evolve(self._state, **kwargs)

    def plot_current_state(self) -> None:
        approx_avg_current = a121_power.converged_average_current(
            self._state.session_config,
            lower_idle_state=self._state.lower_idle_state,
            absolute_tolerance=0.01 * _mA,
            algorithm=self._algorithm,
        )

        if approx_avg_current > 1 * _mA:
            approx_avg_current_formatted = f"{approx_avg_current * _A_to_mA:.0f} mA"
        else:
            milliampere = round(approx_avg_current * _A_to_mA, 2)
            approx_avg_current_formatted = f"{milliampere * _mA_to_uA:.0f} {_MU}A"

        self._plot_widget.clear()
        duration_of_2_actives = a121_power.session(
            self._state.session_config,
            lower_idle_state=self._state.lower_idle_state,
            num_actives=2,
            algorithm=self._algorithm,
        ).duration
        self._plot_item.set_auto_end_x(duration_of_2_actives)

        active_profile = a121_power.group_active(
            self._state.session_config,
            self._state.lower_idle_state,
            algorithm=self._algorithm,
        )

        fifty_first_active_and_idle_profiles = a121_power.session(
            self._state.session_config,
            lower_idle_state=self._state.lower_idle_state,
            num_actives=50,
            algorithm=self._algorithm,
        )

        etc_text = pg.TextItem("and so on ...", anchor=(0, 1))
        etc_text.setPos(fifty_first_active_and_idle_profiles.duration, 0)
        self._plot_widget.addItem(etc_text)

        session_bar_item = PowerCurveBarGraphItem(fifty_first_active_and_idle_profiles)
        self._plot_widget.addItem(session_bar_item)

        power_tag_set = {p.tag for p in fifty_first_active_and_idle_profiles.flat_iter()}

        self._bar_legend.clear()
        for tag in power_tag_set:
            if tag is not None:
                self._bar_legend.addItem(
                    _DummyBarGraphItem(PowerCurveBarGraphItem.tag_color(tag)), tag.name.title()
                )

        if active_profile.duration > 1.0:
            approx_duration_formatted = f"{active_profile.duration:.1f} s"
        else:
            approx_duration_formatted = f"{active_profile.duration * _s_to_ms:.1f} ms"

        region_bounds = (0, active_profile.duration)

        lri = pg.LinearRegionItem(
            values=region_bounds,
            movable=False,
            pen={"color": "#222", "style": Qt.PenStyle.DashLine, "width": 2},
        )

        ti = pg.TextItem(f"Approx. active duration {approx_duration_formatted}", color="#222")

        self._plot_widget.addItem(lri)
        self._plot_widget.addItem(ti)

        hline_item = pg.InfiniteLine(
            pos=approx_avg_current,
            angle=0,
            pen={"color": "#222", "style": Qt.PenStyle.DashLine, "width": 2},
            label=f"Approx. avg. current ({approx_avg_current_formatted})",
            labelOpts={"color": "#222"},
        )
        self._plot_widget.addItem(hline_item)

        rate = a121_power.configured_rate(self._state.session_config)
        if rate is None:
            return

        if active_profile.duration > 1 / rate:
            rate_warning_text = pg.InfiniteLine(
                pos=0.10,
                angle=0,
                label=f"Cannot keep rate.\nMaximum rate is approx.\n{1 / active_profile.duration:.0f} Hz",
                labelOpts={
                    "color": "#000",
                    "fill": WARNING_YELLOW,
                    "border": "#000",
                },
                pen=pg.mkPen(None),
            )
            self._plot_widget.addItem(rate_warning_text)


class _A2EnergyRegionPlot(QWidget):
    @attrs.frozen
    class _State:
        """Whenever this changes, the plot is redrawn (with the new information)"""

        session_config: a2.SessionConfig
        """This received from events"""

        algorithm: a2_power.algo.Algorithm
        aps_sleep_state: (
            a2_power.SensorConstants.ApsIdleState | a2_power.SensorConstants.ApsSleepState
        )
        aps_idle_state: a2_power.SensorConstants.ApsIdleState
        temperature: int = 25

    _MIN_DURATION_S = 20 * _ms
    _MAX_DURATION_S = 10

    def __init__(
        self,
        session_config: a2.SessionConfig,
        aps_sleep_state: a2_power.SensorConstants.ApsIdleState
        | a2_power.SensorConstants.ApsSleepState,
        aps_idle_state: a2_power.SensorConstants.ApsIdleState,
        algorithm: a2_power.algo.Algorithm,
        temperature: int = 25,
    ) -> None:
        super().__init__()

        self._state = self._State(
            session_config,
            algorithm,
            aps_sleep_state,
            aps_idle_state,
            temperature,
        )

        sensor = a2_power.Sensor.at_temperature(temperature)
        duration_of_2_actives = a2_power.session(
            session_config,
            aps_sleep_state=aps_sleep_state,
            aps_idle_state=aps_idle_state,
            aps_active_state=APS_ACTIVE_STATE,
            num_actives=2,
            algorithm=algorithm,
            sensor=sensor,
        ).duration
        self._plot_item = PowerCurvePlotItem(auto_end_x=duration_of_2_actives)
        self._plot_item.autoBtnClicked()

        self._plot_item.setLabel("left", "Current", units="A")
        self._plot_item.setLabel("bottom", "Duration", units="s")
        self._plot_item.setContentsMargins(0, 0, 0, 10)

        self._plot_widget = pg.PlotWidget(plotItem=self._plot_item)
        self._plot_widget.getViewBox().setMouseMode(pg.ViewBox.PanMode)
        y_min = -0.01
        y_max = 0.2
        self._plot_widget.getViewBox().setLimits(
            yMin=y_min, yMax=y_max, minYRange=y_max - y_min, maxYRange=y_max - y_min
        )

        self._bar_legend = pg.graphicsItems.LegendItem.LegendItem(offset=(75, 10))
        self._bar_legend.setParentItem(self._plot_item)
        self._bar_legend.setEnabled(False)

        self._component_legend = pg.graphicsItems.LegendItem.LegendItem(offset=(75, 200))
        self._component_legend.setParentItem(self._plot_item)
        self._component_legend.setEnabled(False)

        self._show_breakdown = True

        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot_widget, 0, 0, 1, 2)
        self.setLayout(layout)

    def evolve_current_state(self, **kwargs: t.Any) -> None:
        self._state = attrs.evolve(self._state, **kwargs)

    def plot_current_state(self) -> None:
        sensor = a2_power.Sensor.at_temperature(self._state.temperature)

        approx_avg_current = a2_power.converged_average_current(
            self._state.session_config,
            aps_sleep_state=self._state.aps_sleep_state,
            aps_idle_state=self._state.aps_idle_state,
            aps_active_state=APS_ACTIVE_STATE,
            absolute_tolerance=0.01 * _mA,
            algorithm=self._state.algorithm,
            sensor=sensor,
        )

        if approx_avg_current > 10 * _mA:
            approx_avg_current_formatted = f"{approx_avg_current * _A_to_mA:.0f} mA"
        elif approx_avg_current > 1 * _mA:
            approx_avg_current_formatted = f"{approx_avg_current * _A_to_mA:.1f} mA"
        else:
            milliampere = round(approx_avg_current * _A_to_mA, 2)
            approx_avg_current_formatted = f"{milliampere * _mA_to_uA:.0f} {_MU}A"

        self._plot_widget.clear()
        duration_of_2_actives = a2_power.session(
            self._state.session_config,
            aps_sleep_state=self._state.aps_sleep_state,
            aps_idle_state=self._state.aps_idle_state,
            aps_active_state=APS_ACTIVE_STATE,
            num_actives=2,
            algorithm=self._state.algorithm,
            sensor=sensor,
        ).duration
        self._plot_item.set_auto_end_x(duration_of_2_actives)

        active_profile = a2_power.frame_active(
            self._state.session_config,
            self._state.aps_idle_state,
            APS_ACTIVE_STATE,
            sensor=sensor,
        )

        fifty_first_active_and_idle_profiles = a2_power.session(
            self._state.session_config,
            aps_sleep_state=self._state.aps_sleep_state,
            aps_idle_state=self._state.aps_idle_state,
            aps_active_state=APS_ACTIVE_STATE,
            num_actives=50,
            algorithm=self._state.algorithm,
            sensor=sensor,
        )

        frame_start = a2_power.frame_start(
            self._state.session_config,
            self._state.aps_sleep_state,
            self._state.aps_idle_state,
            APS_ACTIVE_STATE,
            sensor=sensor,
        )

        etc_text = pg.TextItem("and so on ...", anchor=(0, 1))
        etc_text.setPos(fifty_first_active_and_idle_profiles.duration, 0)
        self._plot_widget.addItem(etc_text)

        show_breakdown = self._show_breakdown and sensor.get_sensor_data().has_current_breakdown
        if show_breakdown:
            stacked_bars = StackedBreakdownBarGroup(fifty_first_active_and_idle_profiles)
            stacked_bars.add_to_plot(self._plot_widget)
        else:
            session_bar_item = PowerCurveBarGraphItem(fifty_first_active_and_idle_profiles)
            self._plot_widget.addItem(session_bar_item)

        power_tag_set = {p.tag for p in fifty_first_active_and_idle_profiles.flat_iter()}

        tag_to_tag_name = {
            a2_power.domain.EnergyRegion.Tag.MEASURE: "Measure",
            a2_power.domain.EnergyRegion.Tag.CALIBRATION: "Calibration",
            a2_power.domain.EnergyRegion.Tag.IDLE: "Idle",
            a2_power.domain.EnergyRegion.Tag.OVERHEAD: "Overhead",
            a2_power.domain.EnergyRegion.Tag.PROCESSING: "Processing",
            a2_power.domain.EnergyRegion.Tag.RS_INITIALIZATION: "RS Initialization",
            a2_power.domain.EnergyRegion.Tag.APS_INITIALIZATION: "APS Initialization",
        }
        self._bar_legend.clear()
        for tag in power_tag_set:
            if tag is not None:
                self._bar_legend.addItem(
                    _DummyBarGraphItem(PowerCurveBarGraphItem.tag_color(tag)),
                    tag_to_tag_name[tag],
                )

        self._component_legend.clear()
        if show_breakdown:
            for idx, component in enumerate(
                _collect_components(fifty_first_active_and_idle_profiles)
            ):
                tile = _make_component_tile(QColor(220, 220, 220), idx)
                self._component_legend.addItem(
                    _DummyPatternBarGraphItem(QBrush(tile)),
                    component,
                )
            self._component_legend.setVisible(True)
        else:
            self._component_legend.setVisible(False)

        if active_profile.duration > 1.0:
            approx_duration_formatted = f"{active_profile.duration:.1f} s"
        elif active_profile.duration > 1.0e-3:
            approx_duration_formatted = f"{active_profile.duration * _s_to_ms:.1f} ms"
        else:
            approx_duration_formatted = f"{active_profile.duration * _s_to_us:.0f} us"

        region_bounds = (frame_start, frame_start + active_profile.duration)

        lri = pg.LinearRegionItem(
            values=region_bounds,
            movable=False,
            pen={"color": "#222", "style": Qt.PenStyle.DashLine, "width": 2},
        )

        ti = pg.TextItem(f"Approx. active duration {approx_duration_formatted}", color="#222")

        self._plot_widget.addItem(lri)
        self._plot_widget.addItem(ti)

        hline_item = pg.InfiniteLine(
            pos=approx_avg_current,
            angle=0,
            pen={"color": "#222", "style": Qt.PenStyle.DashLine, "width": 2},
            label=f"Approx. avg. current ({approx_avg_current_formatted})",
            labelOpts={"color": "#222"},
        )
        self._plot_widget.addItem(hline_item)

        rate = a2_power.configured_rate(self._state.session_config)
        if rate is None:
            return

        if active_profile.duration > 1 / rate:
            rate_warning_text = pg.InfiniteLine(
                pos=0.10,
                angle=0,
                label=f"Cannot keep rate.\nMaximum rate is approx.\n{1 / active_profile.duration:.0f} Hz",
                labelOpts={
                    "color": "#000",
                    "fill": WARNING_YELLOW,
                    "border": "#000",
                },
                pen=pg.mkPen(None),
            )
            self._plot_widget.addItem(rate_warning_text)


class EnergyRegionOutput(QTabWidget):
    INTERESTS: t.ClassVar[set[type]] = {
        A121SessionConfigEvent,
        A2SessionConfigEvent,
        HeatmapCaponConfigEvent,
        HeatmapCoherentConfigEvent,
        HeatmapConventionalConfigEvent,
        HeatmapRobustCaponConfigEvent,
        IdentifiedServiceUninstalledEvent,
        DistanceConfigEvent,
        PresenceConfigEvent,
        ChangeIdEvent,
        BreakdownToggleEvent,
    }
    description: t.ClassVar[str] = "\n\n".join(
        [
            "Visualizes a simulated power curve of a confiugration.",
            f"The spinbox {_X_AXIS_SPINBOX_LABEL!r} controls the end of the X-axis.",
            "Click and hold the plotted rectangles to get a description of that rectangle.",
        ]
    )
    window_title = "Power curve"

    def __init__(self, broker: EventBroker) -> None:
        super().__init__()

        self._tabs: dict[str, _A121EnergyRegionPlot | _A2EnergyRegionPlot] = {}
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("QTabBar { font: bold 14px; font-family: monospace; }")

        broker.install_service(self)
        self.uninstall_function = lambda: broker.uninstall_service(self)
        broker.brief_service(self)

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, A121SessionConfigEvent):
            self._handle_a121_session_config_event(event)
        elif isinstance(event, A2SessionConfigEvent):
            self._handle_a2_session_config_event(event)
        elif isinstance(event, HeatmapCaponConfigEvent):
            self._handle_a2_capon_heatmap_config_event(event)
        elif isinstance(event, HeatmapCoherentConfigEvent):
            self._handle_a2_coherent_heatmap_config_event(event)
        elif isinstance(event, HeatmapConventionalConfigEvent):
            self._handle_a2_conventional_heatmap_config_event(event)
        elif isinstance(event, HeatmapRobustCaponConfigEvent):
            self._handle_a2_robust_capon_heatmap_config_event(event)
        elif isinstance(event, DistanceConfigEvent):
            self._handle_distance_config_event(event)
        elif isinstance(event, PresenceConfigEvent):
            self._handle_presence_config_event(event)
        elif isinstance(event, IdentifiedServiceUninstalledEvent):
            self._handle_identified_service_uninstalled_event(event)
        elif isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        elif isinstance(event, BreakdownToggleEvent):
            self._handle_breakdown_toggle(event)
        else:
            raise NotImplementedError

    def _handle_breakdown_toggle(self, event: BreakdownToggleEvent) -> None:
        for tab in self._tabs.values():
            if isinstance(tab, _A2EnergyRegionPlot):
                tab._show_breakdown = event.enabled
                tab.plot_current_state()

    def _handle_a121_session_config_event(self, event: A121SessionConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A121EnergyRegionPlot(
                event.session_config,
                event.lower_idle_state,
                a121_power.algo.SparseIq(),
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=event.session_config,
                lower_idle_state=event.lower_idle_state,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_a2_session_config_event(self, event: A2SessionConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2EnergyRegionPlot(
                event.session_config,
                event.aps_sleep_state,
                event.aps_idle_state,
                a2_power.algo.SparseIq(),
                temperature=event.temperature,
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=event.session_config,
                algorithm=a2_power.algo.SparseIq(),
                aps_sleep_state=event.aps_sleep_state,
                aps_idle_state=event.aps_idle_state,
                temperature=event.temperature,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_a2_capon_heatmap_config_event(self, event: HeatmapCaponConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2EnergyRegionPlot(
                event.session_config,
                event.aps_sleep_state,
                event.aps_idle_state,
                a2_power.algo.HeatmapCapon.create(event.heatmap_config),
                temperature=event.temperature,
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=event.session_config,
                algorithm=a2_power.algo.HeatmapCapon.create(event.heatmap_config),
                aps_sleep_state=event.aps_sleep_state,
                aps_idle_state=event.aps_idle_state,
                temperature=event.temperature,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_a2_coherent_heatmap_config_event(self, event: HeatmapCoherentConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2EnergyRegionPlot(
                event.session_config,
                event.aps_sleep_state,
                event.aps_idle_state,
                a2_power.algo.HeatmapCoherent.create(event.heatmap_config),
                temperature=event.temperature,
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=event.session_config,
                algorithm=a2_power.algo.HeatmapCoherent.create(event.heatmap_config),
                aps_sleep_state=event.aps_sleep_state,
                aps_idle_state=event.aps_idle_state,
                temperature=event.temperature,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_a2_conventional_heatmap_config_event(
        self, event: HeatmapConventionalConfigEvent
    ) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2EnergyRegionPlot(
                event.session_config,
                event.aps_sleep_state,
                event.aps_idle_state,
                a2_power.algo.HeatmapConventional.create(event.heatmap_config),
                temperature=event.temperature,
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=event.session_config,
                algorithm=a2_power.algo.HeatmapConventional.create(event.heatmap_config),
                aps_sleep_state=event.aps_sleep_state,
                aps_idle_state=event.aps_idle_state,
                temperature=event.temperature,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_a2_robust_capon_heatmap_config_event(
        self, event: HeatmapRobustCaponConfigEvent
    ) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2EnergyRegionPlot(
                event.session_config,
                event.aps_sleep_state,
                event.aps_idle_state,
                a2_power.algo.HeatmapRobustCapon.create(event.heatmap_config),
                temperature=event.temperature,
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=event.session_config,
                algorithm=a2_power.algo.HeatmapRobustCapon.create(event.heatmap_config),
                aps_sleep_state=event.aps_sleep_state,
                aps_idle_state=event.aps_idle_state,
                temperature=event.temperature,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_distance_config_event(self, event: DistanceConfigEvent) -> None:
        session_config = event.translated_session_config

        if event.service_id not in self._tabs:
            plot_widget = _A121EnergyRegionPlot(
                session_config,
                event.lower_idle_state,
                a121_power.algo.Distance(),
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=session_config,
                lower_idle_state=event.lower_idle_state,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_presence_config_event(self, event: PresenceConfigEvent) -> None:
        session_config = event.translated_session_config

        if event.service_id not in self._tabs:
            plot_widget = _A121EnergyRegionPlot(
                session_config,
                event.lower_idle_state,
                a121_power.algo.Presence(),
            )
            self._tabs[event.service_id] = plot_widget

            self.addTab(plot_widget, event.service_id)
            self.setCurrentWidget(plot_widget)
        else:
            self._tabs[event.service_id].evolve_current_state(
                session_config=session_config,
                lower_idle_state=event.lower_idle_state,
            )

        self._tabs[event.service_id].plot_current_state()

    def _handle_identified_service_uninstalled_event(
        self, event: IdentifiedServiceUninstalledEvent
    ) -> None:
        # An output does not necessarily have a tab for every input
        tab_widget = self._tabs.pop(event.id_, None)

        if tab_widget is None:
            return

        tab_index = self.indexOf(tab_widget)
        if tab_index != -1:
            self.removeTab(tab_index)

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        tab_widget = self._tabs.pop(event.old_id, None)
        if tab_widget is not None:
            tab_index = self.indexOf(tab_widget)
            self.setTabText(tab_index, event.new_id)
            self._tabs[event.new_id] = tab_widget
