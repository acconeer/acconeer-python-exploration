# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Type

import numpy as np

from PySide6.QtWidgets import QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorPlotPluginBase,
    ProcessorPluginPreset,
    ProcessorViewPluginBase,
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
    PidgetFactoryMapping,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
    pidgets,
)


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
    def get_processor_cls(cls) -> Type[Processor]:
        return Processor

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
            "threshold": pidgets.FloatParameterWidgetFactory(
                name_label_text="Threshold",
                decimals=1,
                limits=(0.0, 10000),
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig


class PlotPlugin(ProcessorPlotPluginBase[ProcessorResult]):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        (self.distances_m, _) = get_distances_m(sensor_config, metadata)

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
        self.history_plot = self.plot_layout.addPlot(row=2, col=0)
        self.history_plot.setMenuEnabled(False)
        self.history_plot.showGrid(x=True, y=True)
        self.history_plot.addLegend()
        self.history_plot.setLabel("left", "Distance (mm)")
        self.history_plot.setLabel("bottom", "Time (s)")
        self.history_plot.addItem(pg.PlotDataItem())
        self.history_curve = self.history_plot.plot(**feat_kws[0])

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits(tau_decay=0.5, tau_grow=0.1)

    def update(self, processor_result: ProcessorResult) -> None:
        assert processor_result is not None
        assert processor_result.threshold is not None

        sweep = processor_result.lp_abs_sweep
        threshold = processor_result.threshold * np.ones(sweep.size)
        angle_sweep = processor_result.angle_sweep
        peak_loc = processor_result.peak_loc_m
        history = processor_result.distance_history
        rel_time_stamps = processor_result.rel_time_stamps

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


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel, view_widget: QWidget) -> ViewPlugin:
        return ViewPlugin(app_model=app_model, view_widget=view_widget)

    def create_plot_plugin(
        self, app_model: AppModel, plot_layout: pg.GraphicsLayout
    ) -> PlotPlugin:
        return PlotPlugin(app_model=app_model, plot_layout=plot_layout)


PHASE_TRACKING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="phase_tracking",
    title="Phase tracking",
    description="Track target with micrometer precision.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
