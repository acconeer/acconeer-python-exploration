# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import itertools
import operator
import typing as t

import attrs
import typing_extensions as te

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGraphicsSceneMouseEvent,
    QGridLayout,
    QTabWidget,
    QToolTip,
    QWidget,
)

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.a121.model import power
from acconeer.exptool.app.new.ui.icons import WARNING_YELLOW
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)

from .distance_config_input import DistanceConfigEvent
from .presence_config_input import PresenceConfigEvent
from .session_config_input import SessionConfigEvent


_SECONDS_IF_RATE_UNSET = 2e-2
_DURATION_SB_DECIMALS = 4
_DURATION_SB_RANGE = (1e-4, 100)
_DURATION_SB_STEP = 5e-3

_X_AXIS_SPINBOX_LABEL = "X-axis length"
_MU = "\u00b5"

_A_to_mA = _s_to_ms = _mA_to_uA = 1000

_mA = _ms = 1e-3


class PowerCurveBarGraphItem(pg.BarGraphItem):
    def __init__(self, power_profile: power.CompositeRegion) -> None:
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

    @staticmethod
    def tag_color(tag: t.Optional[power.EnergyRegion.Tag]) -> str:
        if tag == power.EnergyRegion.Tag.MEASURE:
            return "cornflowerblue"
        if tag == power.EnergyRegion.Tag.OVERHEAD:
            return "red"
        if tag == power.EnergyRegion.Tag.CALIBRATION:
            return "orange"
        if tag == power.EnergyRegion.Tag.IDLE:
            return "forestgreen"
        if tag == power.EnergyRegion.Tag.COMMUNICATION:
            return "goldenrod"

        return "magenta"

    def _profile_description_at_point(self, x: float, y: float) -> str:
        for end, simple_profile in zip(self._ends, self._power_profile.flat_iter()):
            if x >= end:
                continue

            if y < simple_profile.current:
                return "\n".join(
                    [
                        simple_profile.description,
                        "",
                        "Current:",
                        f"    {simple_profile.current * _A_to_mA:.0f} mA",
                        "Duration:",
                        f"    {simple_profile.duration * _s_to_ms:.1f} ms",
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


class _DummyBarGraphItem(pg.BarGraphItem):
    def __init__(self, color: str) -> None:
        super().__init__(brush=color, x0=1, width=1, y0=1, height=1)


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


class _EnergyRegionPlot(QWidget):
    @attrs.frozen
    class _State:
        """Whenever this changes, the plot is redrawn (with the new information)"""

        session_config: a121.SessionConfig
        """This received from events"""

        lower_idle_state: t.Optional[power.Sensor.LowerIdleState]

    _MIN_DURATION_S = 20 * _ms
    _MAX_DURATION_S = 10

    def __init__(
        self,
        session_config: a121.SessionConfig,
        lower_idle_state: t.Optional[power.Sensor.LowerIdleState],
        algorithm: power.algo.Algorithm,
    ) -> None:
        super().__init__()

        self._state = self._State(session_config, lower_idle_state)
        self._algorithm: te.Final[power.algo.Algorithm] = algorithm

        duration_of_2_actives = power.session(
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
        approx_avg_current = power.converged_average_current(
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
        duration_of_2_actives = power.session(
            self._state.session_config,
            lower_idle_state=self._state.lower_idle_state,
            num_actives=2,
            algorithm=self._algorithm,
        ).duration
        self._plot_item.set_auto_end_x(duration_of_2_actives)

        active_profile = power.group_active(
            self._state.session_config,
            self._state.lower_idle_state,
            algorithm=self._algorithm,
        )

        fifty_first_active_and_idle_profiles = power.session(
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

        power_tag_set = set([p.tag for p in fifty_first_active_and_idle_profiles.flat_iter()])

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

        rate = power.configured_rate(self._state.session_config)
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
        SessionConfigEvent,
        IdentifiedServiceUninstalledEvent,
        DistanceConfigEvent,
        PresenceConfigEvent,
        ChangeIdEvent,
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

        self._tabs: dict[str, _EnergyRegionPlot] = {}
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("QTabBar { font: bold 14px; font-family: monospace; }")

        broker.install_service(self)
        self.uninstall_function = lambda: broker.uninstall_service(self)
        broker.brief_service(self)

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, SessionConfigEvent):
            self._handle_session_config_event(event)
        elif isinstance(event, DistanceConfigEvent):
            self._handle_distance_config_event(event)
        elif isinstance(event, PresenceConfigEvent):
            self._handle_presence_config_event(event)
        elif isinstance(event, IdentifiedServiceUninstalledEvent):
            self._handle_identified_service_uninstalled_event(event)
        elif isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        else:
            raise NotImplementedError

    def _handle_session_config_event(self, event: SessionConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _EnergyRegionPlot(
                event.session_config,
                event.lower_idle_state,
                power.algo.SparseIq(),
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

    def _handle_distance_config_event(self, event: DistanceConfigEvent) -> None:
        session_config = event.translated_session_config

        if event.service_id not in self._tabs:
            plot_widget = _EnergyRegionPlot(
                session_config,
                event.lower_idle_state,
                power.algo.Distance(),
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
            plot_widget = _EnergyRegionPlot(
                session_config,
                event.lower_idle_state,
                power.algo.Presence(),
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
        tab_widget = self._tabs.pop(event.id_)
        tab_index = self.indexOf(tab_widget)
        if tab_index != -1:
            self.removeTab(tab_index)

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        tab_widget = self._tabs.pop(event.old_id, None)
        if tab_widget is not None:
            tab_index = self.indexOf(tab_widget)
            self.setTabText(tab_index, event.new_id)
            self._tabs[event.new_id] = tab_widget
