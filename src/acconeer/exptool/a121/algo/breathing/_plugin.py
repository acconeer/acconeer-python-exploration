# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import time
from enum import Enum, auto
from typing import Callable, Type

import numpy as np

from PySide6.QtGui import QFont
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
from acconeer.exptool.a121.algo.breathing import (
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
            "time_series_length": pidgets.IntPidgetFactory(
                name_label_text="Time series length",
                limits=(0, None),
            ),
            "lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="Time filtering coefficient",
                limits=(0, 1),
                decimals=2,
            ),
            "min_freq": pidgets.FloatSliderPidgetFactory(
                name_label_text="Lower frequency of bandpass filter",
                limits=(0, 1.0),
                decimals=1,
            ),
            "max_freq": pidgets.FloatSliderPidgetFactory(
                name_label_text="Upper frequency of bandpass filter",
                limits=(2.0, 10.0),
                decimals=1,
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig


class PlotPlugin(ProcessorPlotPluginBase[ProcessorResult]):

    _TIME_SERIES_Y_SCALE_MARGIN_M = 0.0025
    _DATA_INIT_DURATION = 5.0

    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:

        pens = [et.utils.pg_pen_cycler(i) for i in range(5)]
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kws = [dict(pen=pen, **symbol_kw) for pen in pens]

        font = QFont()
        font.setPixelSize(16.0)

        # time series plot
        self.time_series_plot = self.plot_layout.addPlot(row=0, col=0)
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.addLegend()
        self.time_series_plot.setLabel("left", "Displacement (m)")
        self.time_series_plot.setLabel("bottom", "Time")
        self.time_series_plot.addItem(pg.PlotDataItem())
        self.time_series_curve = []
        self.time_series_curve.append(self.time_series_plot.plot(**feat_kws[0]))
        self.time_series_curve.append(self.time_series_plot.plot(**feat_kws[1]))

        self.time_series_smooth_limits = et.utils.SmoothLimits()

        self.time_series_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.time_series_text_item.setFont(font)
        self.time_series_text_item.show()
        self.time_series_plot.addItem(self.time_series_text_item)

        # fft plot
        self.fft_plot = self.plot_layout.addPlot(row=1, col=0)
        self.fft_plot.setMenuEnabled(False)
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.addLegend()
        self.fft_plot.setLabel("left", "Power")
        self.fft_plot.setLabel("bottom", "Frequency (Hz)")
        self.fft_plot.addItem(pg.PlotDataItem())
        self.fft_curve = self.fft_plot.plot(**feat_kws[0])
        self.fft_vert_line = pg.InfiniteLine(pen=pens[1])
        self.fft_plot.addItem(self.fft_vert_line)

        self.fft_smooth_max = et.utils.SmoothMax(tau_grow=0.5, tau_decay=2.0)

        self.fft_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.fft_text_item.setFont(font)
        self.fft_text_item.show()
        self.fft_plot.addItem(self.fft_text_item)

        self.start_time = time.time()

    def update(self, processor_result: ProcessorResult) -> None:

        time_series = processor_result.time_series
        distance_to_analyze_m = processor_result.distance_to_analyze_m
        z_abs_lp = processor_result.lp_psd
        freqs = processor_result.freqs
        breathing_rate = processor_result.breathing_rate
        fft_peak_location = processor_result.fft_peak_location

        # time series plot
        self.time_series_curve[0].setData(time_series)
        lim = self.time_series_smooth_limits.update(time_series)

        self.time_series_plot.setYRange(
            lim[0] - self._TIME_SERIES_Y_SCALE_MARGIN_M,
            lim[1] + self._TIME_SERIES_Y_SCALE_MARGIN_M,
        )
        text_y_pos = self.time_series_plot.getAxis("left").range[1] * 0.95
        text_x_pos = self.time_series_plot.getAxis("bottom").range[1] / 2.0
        self.time_series_text_item.setPos(text_x_pos, text_y_pos)
        self.time_series_text_item.setHtml(
            "Distance being visualized: " + "{:.2f}".format(distance_to_analyze_m) + " (m)"
        )

        # fft plot
        if (time.time() - self.start_time) < self._DATA_INIT_DURATION:
            self.fft_curve.setData(freqs, np.zeros_like(freqs))
            self.fft_plot.setYRange(0.0, 1.0)

            text_y_pos = self.fft_plot.getAxis("left").range[1] * 0.95
            text_x_pos = self.fft_plot.getAxis("bottom").range[1] / 2.0
            self.fft_text_item.setHtml("Acquiring data.")
        elif freqs is not None:
            assert z_abs_lp is not None
            assert breathing_rate is not None
            assert fft_peak_location is not None

            self.fft_curve.setData(freqs, z_abs_lp)
            self.fft_vert_line.setValue(fft_peak_location)
            lim = self.fft_smooth_max.update(z_abs_lp)
            self.fft_plot.setYRange(0.0, lim * 1.2)

            text_y_pos = self.fft_plot.getAxis("left").range[1] * 0.95
            text_x_pos = self.fft_plot.getAxis("bottom").range[1] / 2.0

            self.fft_text_item.setHtml(
                "Breathing rate: " + "{:.1f}".format(breathing_rate) + " per minute"
            )
        self.fft_text_item.setPos(text_x_pos, text_y_pos)

    @staticmethod
    def _format_string(string_to_display: str) -> str:
        return (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format(string_to_display)
        )


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


BREATHING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="breathing",
    title="Breathing",
    description="Measure breathing rate.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
