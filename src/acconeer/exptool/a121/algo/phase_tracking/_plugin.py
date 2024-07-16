# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Optional, Type

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorBackendPluginSharedState,
    ProcessorPluginPreset,
    ProcessorViewPluginBase,
    SetupMessage,
)
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.a121.algo.phase_tracking import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_sensor_config,
)
from acconeer.exptool.app.new import (
    AppModel,
    Message,
    PgPlotPlugin,
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    backend,
    pidgets,
)


log = logging.getLogger(__name__)


class PluginPresetId(Enum):
    DEFAULT = auto()


class BackendPlugin(ProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):
    PLUGIN_PRESETS = {
        PluginPresetId.DEFAULT.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_sensor_config()),
            processor_config=BackendPlugin.get_processor_config_cls()(),
        ),
    }

    @classmethod
    def get_processor(cls, state: ProcessorBackendPluginSharedState[ProcessorConfig]) -> Processor:
        if state.metadata is None:
            msg = "metadata is None"
            raise RuntimeError(msg)

        if isinstance(state.metadata, list):
            msg = "metadata is unexpectedly extended"
            raise RuntimeError(msg)

        return Processor(
            sensor_config=state.session_config.sensor_config,
            processor_config=state.processor_config,
            metadata=state.metadata,
        )

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        return get_sensor_config()


class ViewPlugin(ProcessorViewPluginBase[ProcessorConfig]):
    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        # Note: Incomplete mapping
        return {
            "threshold": pidgets.FloatPidgetFactory(
                name_label_text="Threshold:",
                decimals=1,
                limits=(0.0, 10000),
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig


class PlotPlugin(PgPlotPlugin):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)
        self._plot_job: Optional[ProcessorResult] = None
        self._is_setup = False

    def handle_message(self, message: backend.GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        elif isinstance(message, SetupMessage):
            if isinstance(message.metadata, list):
                msg = "Metadata is unexpectedly extended"
                raise RuntimeError(msg)

            self.setup(
                metadata=message.metadata,
                sensor_config=message.session_config.sensor_config,
            )
            self._is_setup = True
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.draw_plot_job(processor_result=self._plot_job)
        finally:
            self._plot_job = None

    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        self.plot_layout.clear()

        assert sensor_config.sweeps_per_frame is not None
        assert sensor_config.sweep_rate is not None

        self.distances_m = get_distances_m(sensor_config, metadata)

        pens = [et.utils.pg_pen_cycler(i) for i in range(3)]
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kws = [dict(pen=pen, **symbol_kw) for pen in pens]

        # sweep and threshold plot
        self.sweep_plot = self.plot_layout.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())
        self.sweeps_curve = [self.sweep_plot.plot(**feat_kw) for feat_kw in feat_kws]
        self.sweep_vertical_line = pg.InfiniteLine(pen=pens[2])
        self.sweep_plot.addItem(self.sweep_vertical_line)
        self.sweep_smooth_max = et.utils.SmoothMax()
        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweeps_curve[0], "Sweep")
        sweep_plot_legend.addItem(self.sweeps_curve[1], "Threshold")

        # argument plot
        argument_plot = self.plot_layout.addPlot(row=1, col=0)
        argument_plot.setMenuEnabled(False)
        argument_plot.showGrid(x=True, y=True)
        argument_plot.addLegend()
        argument_plot.setLabel("bottom", "Distance (m)")
        argument_plot.setLabel("left", "Phase")
        argument_plot.setYRange(-np.pi, np.pi)
        argument_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)
        argument_plot.setYRange(-np.pi, np.pi)
        argument_plot.addItem(pg.ScatterPlotItem())
        self.argument_curve = argument_plot.plot(
            **dict(pen=None, symbol="o", symbolSize=5, symbolPen="k")
        )
        self.argument_vertical_line = pg.InfiniteLine(pen=pens[2])
        argument_plot.addItem(self.argument_vertical_line)

        # history plot
        self.history_plot = self.plot_layout.addPlot(row=0, col=1)
        self.history_plot.setMenuEnabled(False)
        self.history_plot.showGrid(x=True, y=True)
        self.history_plot.addLegend()
        self.history_plot.setLabel("left", "Distance (mm)")
        self.history_plot.setLabel("bottom", "Time (s)")
        self.history_plot.addItem(pg.PlotDataItem())
        self.history_curve = self.history_plot.plot(**feat_kws[0])

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits(tau_decay=0.2, tau_grow=0.1)

        # IQ plot
        self.iq_plot = self.plot_layout.addPlot(row=1, col=1)
        self.iq_plot.setMenuEnabled(False)
        self.iq_plot.setMouseEnabled(x=False, y=False)
        self.iq_plot.hideButtons()
        et.utils.pg_setup_polar_plot(self.iq_plot, 1)
        self.iq_curve = self.iq_plot.plot(pen=et.utils.pg_pen_cycler())
        self.iq_scatter = pg.ScatterPlotItem(brush=pg.mkBrush(et.utils.color_cycler()), size=15)
        self.iq_plot.addItem(self.iq_scatter)

        self.smooth_max = et.utils.SmoothMax(
            sensor_config.sweep_rate / sensor_config.sweeps_per_frame
        )

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        assert processor_result is not None
        assert processor_result.threshold is not None

        sweep = processor_result.lp_abs_sweep
        threshold = processor_result.threshold * np.ones(sweep.size)
        angle_sweep = processor_result.angle_sweep
        peak_loc = processor_result.peak_loc_m
        history = processor_result.distance_history
        rel_time_stamps = processor_result.rel_time_stamps
        iq_history = processor_result.iq_history

        # update sweep plot
        self.sweeps_curve[0].setData(self.distances_m, sweep)
        self.sweeps_curve[1].setData(self.distances_m, threshold)
        max_val_in_sweep_plot = max(np.max(sweep), np.max(threshold))
        self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_sweep_plot))

        # update argument plot
        self.argument_curve.setData(self.distances_m, angle_sweep)

        if peak_loc is not None:
            # update vertical lines
            self.sweep_vertical_line.setValue(peak_loc)
            self.argument_vertical_line.setValue(peak_loc)
            self.sweep_vertical_line.show()
            self.argument_vertical_line.show()
        else:
            self.sweep_vertical_line.hide()
            self.argument_vertical_line.hide()

        if history.shape[0] != 0:
            # update history plot
            self.history_curve.setData(rel_time_stamps, history)
            lims = self.distance_hist_smooth_lim.update(history)
            self.history_plot.setYRange(lims[0], lims[1])
        self.history_plot.setXRange(-Processor.TIME_HORIZON_S, 0)

        if not np.all(np.isnan(iq_history)):
            m = self.smooth_max.update(np.abs(iq_history))
            norm_iq_history = iq_history / m
            self.iq_curve.setData(norm_iq_history.real, norm_iq_history.imag)
            self.iq_scatter.setData([norm_iq_history[0].real], [norm_iq_history[0].imag])
        else:
            self.iq_curve.setData([], [])
            self.iq_scatter.setData([], [])


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


PHASE_TRACKING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="phase_tracking",
    title="Phase tracking",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/phase_tracking.html",
    description="Track target with micrometer precision.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
