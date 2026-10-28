# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import collections
import copy
import functools
import itertools
import typing as t

import typing_extensions as te

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool import a2, a121
from acconeer.exptool.a2.model import power as a2_power
from acconeer.exptool.a121._core import utils as core_utils
from acconeer.exptool.a121.model import power as a121_power
from acconeer.exptool.app.new.ui.icons import WARNING_YELLOW
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)
from acconeer.exptool.utils import pg_pen_cycler

from ._a2_power_selections import APS_ACTIVE_STATE
from .a2_heatmap_capon_config_input import HeatmapCaponConfigEvent
from .a2_heatmap_coherent_config_input import HeatmapCoherentConfigEvent
from .a2_heatmap_conventional_config_input import HeatmapConventionalConfigEvent
from .a2_heatmap_robust_capon_config_input import HeatmapRobustCaponConfigEvent
from .a2_session_config_input import SessionConfigEvent as A2SessionConfigEvent
from .a121_session_config_input import SessionConfigEvent as A121SessionConfigEvent
from .distance_config_input import DistanceConfigEvent
from .presence_config_input import PresenceConfigEvent


_T = t.TypeVar("_T")


def incremental_plot(
    xs: list[float],
    f: t.Callable[[float], float],
    ordering_strategy: t.Callable[[int], t.Iterable[int]],
) -> t.Iterator[tuple[list[float], list[float]]]:
    """Generator that adds one (x, y)-point to the plot each time it's iterated"""
    done: list[tuple[float, float]] = []

    for i in ordering_strategy(len(xs)):
        x = xs[i]

        done += [(x, f(x))]
        done.sort(key=lambda t: t[0])

        all_xs = [done_x for done_x, _ in done]
        all_ys = [done_y for _, done_y in done]
        yield (all_xs, all_ys)


class _A121PowerConsumptionVsRatePlot(pg.PlotWidget):
    def __init__(self, algorithm: a121_power.algo.Algorithm) -> None:
        super().__init__()

        self._algorithm: te.Final[a121_power.algo.Algorithm] = algorithm

        self.getPlotItem().setLabel("bottom", "Update rate", units="Hz")
        self.getPlotItem().setLabel("left", "Sensor + XM125", units="A")
        self.getPlotItem().setContentsMargins(0, 0, 0, 10)
        self.getPlotItem().addLegend()
        self.getViewBox().setMouseMode(pg.ViewBox.PanMode)

        self._ready_plotter: t.Iterator[tuple[list[float], list[float]]] = iter([])
        self._sleep_plotter: t.Iterator[tuple[list[float], list[float]]] = iter([])
        self._deep_sleep_plotter: t.Iterator[tuple[list[float], list[float]]] = iter([])
        self._hibernate_plotter: t.Iterator[tuple[list[float], list[float]]] = iter([])
        self._off_plotter: t.Iterator[tuple[list[float], list[float]]] = iter([])

        self._ready_curve: t.Optional[pg.PlotDataItem] = None
        self._sleep_curve: t.Optional[pg.PlotDataItem] = None
        self._deep_sleep_curve: t.Optional[pg.PlotDataItem] = None
        self._hibernate_curve: t.Optional[pg.PlotDataItem] = None
        self._off_curve: t.Optional[pg.PlotDataItem] = None

        self._plot_increment_timer = QTimer()
        self._plot_increment_timer.timeout.connect(self._increment_plots)

    @staticmethod
    def _get_update_rates(update_rate: float) -> list[float]:
        return list(
            itertools.takewhile(
                lambda e: e < update_rate * 1.5,
                itertools.chain(
                    [i / 100 for i in range(1, 100)],  # [0.01, 0.99] in 0.01 steps
                    [1 + i / 10 for i in range(90)],  # [1, 9.9] in 0.1 steps
                    itertools.count(start=10),  # [10, inf) in 1.0 steps
                ),
            )
        )

    @staticmethod
    def _evolve_config(
        config: a121.SessionConfig,
        *,
        update_rate: t.Optional[float] = None,
        inter_frame_idle_state: t.Optional[a121.IdleState] = None,
    ) -> a121.SessionConfig:
        config_copy = copy.deepcopy(config)

        if update_rate is not None:
            config_copy.update_rate = update_rate

        if inter_frame_idle_state is not None:
            last_sensor_config = list(config_copy.groups[-1].values())[-1]
            last_sensor_config.inter_frame_idle_state = inter_frame_idle_state

        return config_copy

    def _increment_plots(self) -> None:
        (self._sleep_curve, sleep_done) = self._increment_plot(
            "Sleep", pg_pen_cycler(0), self._sleep_plotter, self._sleep_curve
        )
        (self._deep_sleep_curve, deep_sleep_done) = self._increment_plot(
            "Deep sleep", pg_pen_cycler(1), self._deep_sleep_plotter, self._deep_sleep_curve
        )
        (self._hibernate_curve, hibernate_done) = self._increment_plot(
            "Hibernate", pg_pen_cycler(2), self._hibernate_plotter, self._hibernate_curve
        )
        (self._off_curve, off_done) = self._increment_plot(
            "Off", pg_pen_cycler(3), self._off_plotter, self._off_curve
        )
        (self._ready_curve, _) = self._increment_plot(
            "Ready", pg_pen_cycler(4), self._ready_plotter, self._ready_curve
        )

        if all([sleep_done, deep_sleep_done, hibernate_done, off_done]):
            self._plot_increment_timer.stop()

    def _increment_plot(
        self,
        name: str,
        pen: t.Any,
        incremental_plotter: t.Iterator[tuple[list[float], list[float]]],
        reused_curve: t.Optional[pg.PlotDataItem],
    ) -> tuple[pg.PlotDataItem, bool]:
        """
        Plots the next increment of incremental_plotter.
        If reused_curve is None, a new curve will be created with name and pen.

        Returns the updated curve (migth be the same as reused_curve) and whether
        plotting is completed
        """
        try:
            (xs, ys) = next(incremental_plotter)
        except StopIteration:
            return (reused_curve, True)
        else:
            if reused_curve is None:
                return (
                    self.plot(xs, ys, name=name, pen=pen),
                    False,
                )
            else:
                reused_curve.setData(xs, ys)
                return (reused_curve, False)

    @staticmethod
    def _will_keep_rate(
        config: a121.SessionConfig,
        lower_idle_state: t.Optional[a121_power.Sensor.LowerIdleState],
        algorithm: a121_power.algo.Algorithm,
    ) -> bool:
        rate = a121_power.configured_rate(config)

        if rate is None:
            return True

        active = a121_power.group_active(config, lower_idle_state, algorithm)
        return active.duration < 1 / rate

    def update_power_curves(
        self,
        config: a121.SessionConfig,
        lower_idle_state: t.Optional[a121_power.Sensor.LowerIdleState],
    ) -> None:
        self._plot_increment_timer.stop()
        self.clear()

        configured_rate = a121_power.configured_rate(config)

        if configured_rate is None:
            self.disableAutoRange()
            ((_, x_max), (_, _)) = self.viewRange()

            text_item = pg.InfiniteLine(
                pos=0.75 * x_max,
                angle=0,
                label="Set update rate to compare\npower states over rates",
                labelOpts={"color": "#111", "fill": "#ddd"},
                pen=pg.mkPen(None),
            )
            self.addItem(text_item)
            return

        update_rates = self._get_update_rates(configured_rate)

        self.enableAutoRange()
        self.setXRange(min(update_rates), max(update_rates))

        self._ready_curve = None
        self._sleep_curve = None
        self._deep_sleep_curve = None
        self._hibernate_curve = None
        self._off_curve = None
        self._increment_plots()
        self.addItem(
            pg.ScatterPlotItem(
                [configured_rate],
                [
                    a121_power.converged_average_current(
                        config,
                        lower_idle_state=lower_idle_state,
                        absolute_tolerance=1e-3,
                        algorithm=self._algorithm,
                    )
                ],
                name="Current config",
            )
        )

        curves_that_wont_keep_rate = []
        if any(
            sensor_config.inter_frame_idle_state == a121.IdleState.READY
            for sensor_config in core_utils.iterate_extended_structure_values(config.groups)
        ):
            ready_config_evolver = functools.partial(
                self._evolve_config,
                inter_frame_idle_state=a121.IdleState.READY,
            )
            if not self._will_keep_rate(
                ready_config_evolver(config, update_rate=max(update_rates)),
                lower_idle_state=None,
                algorithm=self._algorithm,
            ):
                curves_that_wont_keep_rate += ["Ready"]

            def ready_f(update_rate: float) -> float:
                return a121_power.converged_average_current(
                    ready_config_evolver(config, update_rate=update_rate),
                    lower_idle_state=None,
                    absolute_tolerance=1e-3,
                    algorithm=self._algorithm,
                )

            self._ready_plotter = incremental_plot(update_rates, ready_f, ordering_strategy=range)

        sleep_config_evolver = functools.partial(
            self._evolve_config,
            inter_frame_idle_state=a121.IdleState.SLEEP,
        )
        if not self._will_keep_rate(
            sleep_config_evolver(config, update_rate=max(update_rates)),
            lower_idle_state=None,
            algorithm=self._algorithm,
        ):
            curves_that_wont_keep_rate += ["Sleep"]

        def sleep_f(update_rate: float) -> float:
            return a121_power.converged_average_current(
                sleep_config_evolver(config, update_rate=update_rate),
                lower_idle_state=None,
                absolute_tolerance=1e-3,
                algorithm=self._algorithm,
            )

        self._sleep_plotter = incremental_plot(update_rates, sleep_f, ordering_strategy=range)

        deep_sleep_config_evolver = functools.partial(
            self._evolve_config,
            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
        )
        if not self._will_keep_rate(
            deep_sleep_config_evolver(config, update_rate=max(update_rates)),
            lower_idle_state=None,
            algorithm=self._algorithm,
        ):
            curves_that_wont_keep_rate += ["Deep Sleep"]

        def deep_sleep_f(update_rate: float) -> float:
            return a121_power.converged_average_current(
                deep_sleep_config_evolver(config, update_rate=update_rate),
                lower_idle_state=None,
                absolute_tolerance=1e-3,
                algorithm=self._algorithm,
            )

        self._deep_sleep_plotter = incremental_plot(
            update_rates, deep_sleep_f, ordering_strategy=range
        )

        if not self._will_keep_rate(
            self._evolve_config(config, update_rate=max(update_rates)),
            lower_idle_state=a121_power.Sensor.IdleState.HIBERNATE,
            algorithm=self._algorithm,
        ):
            curves_that_wont_keep_rate += ["Hibernate"]

        def hibernate_f(update_rate: float) -> float:
            return a121_power.converged_average_current(
                self._evolve_config(config, update_rate=update_rate),
                lower_idle_state=a121_power.Sensor.IdleState.HIBERNATE,
                absolute_tolerance=1e-3,
                algorithm=self._algorithm,
            )

        self._hibernate_plotter = incremental_plot(
            update_rates, hibernate_f, ordering_strategy=range
        )

        if not self._will_keep_rate(
            self._evolve_config(config, update_rate=max(update_rates)),
            lower_idle_state=a121_power.Sensor.IdleState.OFF,
            algorithm=self._algorithm,
        ):
            curves_that_wont_keep_rate += ["Off"]

        def off_f(update_rate: float) -> float:
            return a121_power.converged_average_current(
                self._evolve_config(config, update_rate=update_rate),
                lower_idle_state=a121_power.Sensor.IdleState.OFF,
                absolute_tolerance=1e-3,
                algorithm=self._algorithm,
            )

        self._off_plotter = incremental_plot(update_rates, off_f, ordering_strategy=range)

        if curves_that_wont_keep_rate:
            rate_warning_text = pg.InfiniteLine(
                pos=0.003,
                angle=0,
                label=(
                    "The following curves cannot keep\n"
                    + "rate at some point in the plot:\n\n"
                    + "\n".join(f" - {name}" for name in curves_that_wont_keep_rate)
                ),
                labelOpts={
                    "color": "#0008",
                    "fill": pg.mkBrush(WARNING_YELLOW + "88"),
                    "border": "#0008",
                },
                pen=pg.mkPen(None),
            )
            self.addItem(rate_warning_text)

        self._plot_increment_timer.start(10)


class _A2PowerConsumptionVsRatePlot(pg.PlotWidget):
    def __init__(self) -> None:
        super().__init__()

        self.getPlotItem().setLabel("bottom", "Update rate", units="Hz")
        self.getPlotItem().setLabel("left", "Current", units="A")
        self.getPlotItem().setContentsMargins(0, 0, 0, 10)
        self.getPlotItem().addLegend()
        self.getViewBox().setMouseMode(pg.ViewBox.PanMode)

        self._curves: dict[str, t.Optional[pg.PlotDataItem]] = {}
        self._curve_pens: dict[str, t.Any] = {}
        self._active_plotters: collections.deque[
            tuple[str, t.Iterator[tuple[list[float], list[float]]]]
        ] = collections.deque()

        self._plot_timer = QTimer()
        self._plot_timer.timeout.connect(self._process_next_point)

    @staticmethod
    def _get_update_rates(update_rate: float) -> list[float]:
        return list(
            itertools.takewhile(
                lambda e: e < update_rate * 1.5,
                itertools.chain(
                    [i / 100 for i in range(1, 100)],  # [0.01, 0.99] in 0.01 steps
                    [1 + i / 10 for i in range(90)],  # [1, 9.9] in 0.1 steps
                    itertools.count(start=10),  # [10, inf) in 1.0 steps
                ),
            )
        )

    @staticmethod
    def _evolve_config(
        config: a2.SessionConfig,
        *,
        update_rate: t.Optional[float] = None,
        frame_rate: t.Optional[float] = None,
        inter_frame_idle_state: t.Optional[a2.IdleState] = None,
    ) -> a2.SessionConfig:
        config_copy = copy.deepcopy(config)

        if update_rate is not None:
            config_copy.update_rate = update_rate

        if frame_rate is not None:
            config_copy.sensor_config.frame_rate = frame_rate

        if inter_frame_idle_state is not None:
            config_copy.sensor_config.inter_frame_idle_state = inter_frame_idle_state

        return config_copy

    def _process_next_point(self) -> None:
        """Advance one plotter by one point, then yield to the event loop."""
        if not self._active_plotters:
            self._plot_timer.stop()
            return

        name, plotter = self._active_plotters[0]
        try:
            xs, ys = next(plotter)
            curve = self._curves.get(name)
            if curve is None:
                pen = self._curve_pens.get(name)
                self._curves[name] = self.plot(xs, ys, name=name, pen=pen)
            else:
                curve.setData(xs, ys)
            self._active_plotters.rotate(-1)
        except StopIteration:
            self._active_plotters.popleft()
            if not self._active_plotters:
                self._plot_timer.stop()

    @staticmethod
    def _will_keep_rate(
        config: a2.SessionConfig,
        aps_sleep_state: t.Union[
            a2_power.SensorConstants.ApsIdleState, a2_power.SensorConstants.ApsSleepState
        ],
        aps_idle_state: a2_power.SensorConstants.ApsIdleState,
        algorithm: a2_power.algo.Algorithm,
    ) -> bool:
        rate = a2_power.configured_rate(config)

        if rate is None:
            return True

        # For now we don't have support for groups in the A2 RC. This will become relevant once we
        # add support for detectors and ref apps.
        active = a2_power.group_active(
            config, aps_sleep_state, aps_idle_state, APS_ACTIVE_STATE, algorithm
        )
        return active.duration < 1 / rate

    def update_power_curves(
        self,
        config: a2.SessionConfig,
        aps_sleep_state: t.Union[
            a2_power.SensorConstants.ApsIdleState, a2_power.SensorConstants.ApsSleepState
        ],
        aps_idle_state: a2_power.SensorConstants.ApsIdleState,
        algorithm: a2_power.algo.Algorithm,
    ) -> None:
        self._plot_timer.stop()
        self._active_plotters.clear()
        self._curves = {}
        self._curve_pens = {}
        self.clear()

        configured_rate = a2_power.configured_rate(config)

        if configured_rate is None:
            self.disableAutoRange()
            ((_, x_max), (_, _)) = self.viewRange()

            text_item = pg.InfiniteLine(
                pos=0.75 * x_max,
                angle=0,
                label="Set update rate to compare\npower states over rates",
                labelOpts={"color": "#111", "fill": "#ddd"},
                pen=pg.mkPen(None),
            )
            self.addItem(text_item)
            return

        update_rates = self._get_update_rates(configured_rate)

        self.enableAutoRange()
        self.setXRange(min(update_rates), max(update_rates))

        self.addItem(
            pg.ScatterPlotItem(
                [configured_rate],
                [
                    a2_power.converged_average_current(
                        config,
                        aps_sleep_state=aps_sleep_state,
                        aps_idle_state=aps_idle_state,
                        aps_active_state=APS_ACTIVE_STATE,
                        absolute_tolerance=1e-3,
                        algorithm=algorithm,
                    )
                ],
                name="Current config",
            )
        )

        curves_that_wont_keep_rate: list[str] = []

        # One deepcopy for all _will_keep_rate checks
        max_rate_config = self._evolve_config(config, update_rate=max(update_rates))

        if config.update_rate is not None:
            _sleep_specs: list[
                tuple[
                    str,
                    t.Union[
                        a2_power.SensorConstants.ApsIdleState,
                        a2_power.SensorConstants.ApsSleepState,
                    ],
                    int,
                ]
            ] = [
                ("HF WFI", a2_power.SensorConstants.ApsIdleState.APS_HF_WFI, 0),
                ("MF WFI", a2_power.SensorConstants.ApsIdleState.APS_MF_WFI, 1),
                ("LF WFI", a2_power.SensorConstants.ApsIdleState.APS_LF_WFI, 2),
                (
                    "SHALLOW SLEEP",
                    a2_power.SensorConstants.ApsSleepState.SHALLOW_SLEEP,
                    3,
                ),
                (
                    "DEEP SLEEP",
                    a2_power.SensorConstants.ApsSleepState.DEEP_SLEEP,
                    4,
                ),
                (
                    "ULTRA DEEP SLEEP",
                    a2_power.SensorConstants.ApsSleepState.ULTRA_DEEP_SLEEP,
                    5,
                ),
            ]

            for curve_name, sleep_st, pen_idx in _sleep_specs:
                self._curve_pens[curve_name] = pg_pen_cycler(pen_idx)

                if not self._will_keep_rate(
                    max_rate_config,
                    aps_sleep_state=sleep_st,
                    aps_idle_state=aps_idle_state,
                    algorithm=algorithm,
                ):
                    curves_that_wont_keep_rate.append(curve_name)

                def _make_f(
                    _sleep_st: t.Union[
                        a2_power.SensorConstants.ApsIdleState,
                        a2_power.SensorConstants.ApsSleepState,
                    ] = sleep_st,
                ) -> t.Callable[[float], float]:
                    cfg = copy.deepcopy(config)

                    def f(update_rate: float) -> float:
                        cfg.update_rate = update_rate
                        return a2_power.converged_average_current(
                            cfg,
                            aps_sleep_state=_sleep_st,
                            aps_idle_state=aps_idle_state,
                            aps_active_state=APS_ACTIVE_STATE,
                            absolute_tolerance=1e-3,
                            algorithm=algorithm,
                        )

                    return f

                self._active_plotters.append(
                    (
                        curve_name,
                        incremental_plot(
                            update_rates,
                            _make_f(),
                            ordering_strategy=range,
                        ),
                    )
                )

        else:
            max_frame_config = self._evolve_config(config, frame_rate=max(update_rates))

            if config.sensor_config.inter_frame_idle_state == a2.IdleState.ARMED:
                self._curve_pens["Armed"] = pg_pen_cycler(7)
                if not self._will_keep_rate(
                    max_frame_config,
                    aps_sleep_state=aps_sleep_state,
                    aps_idle_state=aps_idle_state,
                    algorithm=algorithm,
                ):
                    curves_that_wont_keep_rate.append("Armed")

                armed_cfg = copy.deepcopy(config)

                def armed_f(frame_rate: float) -> float:
                    armed_cfg.sensor_config.frame_rate = frame_rate
                    return a2_power.converged_average_current(
                        armed_cfg,
                        aps_sleep_state=aps_sleep_state,
                        aps_idle_state=aps_idle_state,
                        aps_active_state=APS_ACTIVE_STATE,
                        absolute_tolerance=1e-3,
                        algorithm=algorithm,
                    )

                self._active_plotters.append(
                    (
                        "Armed",
                        incremental_plot(
                            update_rates,
                            armed_f,
                            ordering_strategy=range,
                        ),
                    )
                )

            self._curve_pens["Ready"] = pg_pen_cycler(6)
            ready_cfg = self._evolve_config(
                config,
                inter_frame_idle_state=a2.IdleState.READY,
            )
            if not self._will_keep_rate(
                self._evolve_config(
                    config,
                    frame_rate=max(update_rates),
                    inter_frame_idle_state=a2.IdleState.READY,
                ),
                aps_sleep_state=aps_sleep_state,
                aps_idle_state=aps_idle_state,
                algorithm=algorithm,
            ):
                curves_that_wont_keep_rate.append("Ready")

            def ready_f(frame_rate: float) -> float:
                ready_cfg.sensor_config.frame_rate = frame_rate
                return a2_power.converged_average_current(
                    ready_cfg,
                    aps_sleep_state=aps_sleep_state,
                    aps_idle_state=aps_idle_state,
                    aps_active_state=APS_ACTIVE_STATE,
                    absolute_tolerance=1e-3,
                    algorithm=algorithm,
                )

            self._active_plotters.append(
                (
                    "Ready",
                    incremental_plot(
                        update_rates,
                        ready_f,
                        ordering_strategy=range,
                    ),
                )
            )

        if curves_that_wont_keep_rate:
            rate_warning_text = pg.InfiniteLine(
                pos=0.003,
                angle=0,
                label=(
                    "The following curves cannot keep\n"
                    + "rate at some point in the plot:\n\n"
                    + "\n".join(f" - {name}" for name in curves_that_wont_keep_rate)
                ),
                labelOpts={
                    "color": "#0008",
                    "fill": pg.mkBrush(WARNING_YELLOW + "88"),
                    "border": "#0008",
                },
                pen=pg.mkPen(None),
            )
            self.addItem(rate_warning_text)

        if self._active_plotters:
            self._plot_timer.start(0)


class PowerConsumptionVsRateOutput(QWidget):
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
    }
    description: t.ClassVar[str] = "\n\n".join(
        [
            "Compares power consumption and rate for different power- & inter frame idle states.",
            "NOTE: A curve flatlining means that the rate is the maximum for that power state.",
        ]
    )
    window_title = "Power consumption vs rate"

    def __init__(
        self,
        broker: EventBroker,
    ) -> None:
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.setStyleSheet("QTabBar { font: bold 14px; font-family: monospace; }")
        self._tab_widget = QTabWidget()
        self._tabs: dict[
            str, t.Union[_A121PowerConsumptionVsRatePlot, _A2PowerConsumptionVsRatePlot]
        ] = {}

        layout.addWidget(self._tab_widget)
        self.setLayout(layout)

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
        else:
            raise NotImplementedError

    def _handle_a121_session_config_event(self, event: A121SessionConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A121PowerConsumptionVsRatePlot(algorithm=a121_power.algo.SparseIq())
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.session_config,  # type: ignore[arg-type]
            event.lower_idle_state,  # type: ignore[arg-type]
        )

    def _handle_a2_session_config_event(self, event: A2SessionConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2PowerConsumptionVsRatePlot()
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.session_config,  # type: ignore[arg-type]
            event.aps_sleep_state,  # type: ignore[arg-type]
            event.aps_idle_state,
            algorithm=a2_power.algo.SparseIq(),
        )

    def _handle_a2_capon_heatmap_config_event(self, event: HeatmapCaponConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2PowerConsumptionVsRatePlot()
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.session_config,  # type: ignore[arg-type]
            event.aps_sleep_state,  # type: ignore[arg-type]
            event.aps_idle_state,
            algorithm=a2_power.algo.HeatmapCapon.create(event.heatmap_config),
        )

    def _handle_a2_coherent_heatmap_config_event(self, event: HeatmapCoherentConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2PowerConsumptionVsRatePlot()
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.session_config,  # type: ignore[arg-type]
            event.aps_sleep_state,  # type: ignore[arg-type]
            event.aps_idle_state,
            algorithm=a2_power.algo.HeatmapCoherent.create(event.heatmap_config),
        )

    def _handle_a2_conventional_heatmap_config_event(
        self, event: HeatmapConventionalConfigEvent
    ) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2PowerConsumptionVsRatePlot()
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.session_config,  # type: ignore[arg-type]
            event.aps_sleep_state,  # type: ignore[arg-type]
            event.aps_idle_state,
            algorithm=a2_power.algo.HeatmapConventional.create(event.heatmap_config),
        )

    def _handle_a2_robust_capon_heatmap_config_event(
        self, event: HeatmapRobustCaponConfigEvent
    ) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A2PowerConsumptionVsRatePlot()
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.session_config,  # type: ignore[arg-type]
            event.aps_sleep_state,  # type: ignore[arg-type]
            event.aps_idle_state,
            algorithm=a2_power.algo.HeatmapRobustCapon.create(event.heatmap_config),
        )

    def _handle_distance_config_event(self, event: DistanceConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A121PowerConsumptionVsRatePlot(algorithm=a121_power.algo.Distance())
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.translated_session_config,  # type: ignore[arg-type]
            event.lower_idle_state,  # type: ignore[arg-type]
        )

    def _handle_presence_config_event(self, event: PresenceConfigEvent) -> None:
        if event.service_id not in self._tabs:
            plot_widget = _A121PowerConsumptionVsRatePlot(algorithm=a121_power.algo.Presence())
            self._tabs[event.service_id] = plot_widget

            self._tab_widget.addTab(plot_widget, event.service_id)
            self._tab_widget.setCurrentWidget(plot_widget)

        self._tabs[event.service_id].update_power_curves(  # type: ignore[call-arg]
            event.translated_session_config,  # type: ignore[arg-type]
            event.lower_idle_state,  # type: ignore[arg-type]
        )

    def _handle_identified_service_uninstalled_event(
        self, event: IdentifiedServiceUninstalledEvent
    ) -> None:
        # An output does not necessarily have a tab for every input
        tab_widget = self._tabs.pop(event.id_, None)

        if tab_widget is None:
            return

        tab_index = self._tab_widget.indexOf(tab_widget)
        if tab_index != -1:
            self._tab_widget.removeTab(tab_index)

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        tab_widget = self._tabs.pop(event.old_id, None)
        if tab_widget is not None:
            tab_index = self._tab_widget.indexOf(tab_widget)
            self._tab_widget.setTabText(tab_index, event.new_id)
            self._tabs[event.new_id] = tab_widget
