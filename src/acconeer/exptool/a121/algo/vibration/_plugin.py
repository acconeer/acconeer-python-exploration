# Copyright (c) Acconeer AB, 2023
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
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo.vibration import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    ReportedDisplacement,
    get_high_frequency_processor_config,
    get_high_frequency_sensor_config,
    get_low_frequency_processor_config,
    get_low_frequency_sensor_config,
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
    LOW_FREQ = auto()
    HIGH_FREQ = auto()


class BackendPlugin(ProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):
    PLUGIN_PRESETS = {
        PluginPresetId.LOW_FREQ.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_low_frequency_sensor_config()),
            processor_config=get_low_frequency_processor_config(),
        ),
        PluginPresetId.HIGH_FREQ.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_high_frequency_sensor_config()),
            processor_config=get_high_frequency_processor_config(),
        ),
    }

    @classmethod
    def get_processor(cls, state: ProcessorBackendPluginSharedState[ProcessorConfig]) -> Processor:
        if state.metadata is None:
            raise RuntimeError("metadata is None")

        if isinstance(state.metadata, list):
            raise RuntimeError("metadata is unexpectedly extended")

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
        return get_low_frequency_sensor_config()


class ViewPlugin(ProcessorViewPluginBase[ProcessorConfig]):
    @classmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        # Note: Incomplete mapping
        return {
            "time_series_length": pidgets.IntPidgetFactory(
                name_label_text="Time series length:",
                limits=(0, None),
            ),
            "lp_coeff": pidgets.FloatSliderPidgetFactory(
                name_label_text="Time filtering coefficient:",
                suffix="",
                limits=(0, 1),
                decimals=2,
            ),
            "threshold_margin": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold margin:",
                suffix="um",
                limits=(0, 100),
                decimals=1,
            ),
            "amplitude_threshold": pidgets.FloatPidgetFactory(
                name_label_text="Amplitude threshold:",
                decimals=0,
                limits=(0, None),
            ),
            "reported_displacement_mode": pidgets.EnumPidgetFactory(
                name_label_text="Displacement mode:",
                enum_type=ReportedDisplacement,
                label_mapping={
                    ReportedDisplacement.AMPLITUDE: "Amplitude",
                    ReportedDisplacement.PEAK2PEAK: "Peak to peak",
                },
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
                raise RuntimeError("Metadata is unexpectedly extended")

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

        self.meas_dist_m = sensor_config.start_point * APPROX_BASE_STEP_LENGTH_M

        pen_blue = et.utils.pg_pen_cycler(0)
        pen_orange = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(0)
        brush_dot = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw_blue = dict(pen=pen_blue, **symbol_kw)
        feat_kw_orange = dict(pen=pen_orange)
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_dot, symbolPen="k")

        # presence plot
        self.object_detection_plot = pg.PlotItem()
        self.object_detection_plot.setMenuEnabled(False)
        self.object_detection_plot.showGrid(x=False, y=True)
        self.object_detection_plot.setLabel("left", "Max amplitude")
        self.object_detection_plot.setLabel("bottom", "Distance (m)")
        self.object_detection_plot.setXRange(self.meas_dist_m - 0.001, self.meas_dist_m + 0.001)
        self.presence_curve = self.object_detection_plot.plot(
            **dict(pen=pen_blue, **symbol_dot_kw)
        )

        self.presence_threshold = pg.InfiniteLine(pen=pen_blue, angle=0)
        self.object_detection_plot.addItem(self.presence_threshold)
        self.presence_threshold.show()

        self.smooth_max_presence = et.utils.SmoothMax(tau_decay=10.0)

        # sweep and threshold plot
        self.time_series_plot = pg.PlotItem()
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.setLabel("left", "Displacement (<font>&mu;</font>m)")
        self.time_series_plot.setLabel("bottom", "History")
        self.time_series_curve = self.time_series_plot.plot(**feat_kw_blue)

        self.time_series_plot.setYRange(-1000, 1000)
        self.time_series_plot.setXRange(0, 1024)

        self.text_item_time_series = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.text_item_time_series.hide()
        self.time_series_plot.addItem(self.text_item_time_series)

        sublayout = self.plot_layout.addLayout(row=0, col=0)
        sublayout.layout.setColumnStretchFactor(1, 5)
        sublayout.addItem(self.object_detection_plot, row=0, col=0)
        sublayout.addItem(self.time_series_plot, row=0, col=1)

        self.smooth_lim_time_series = et.utils.SmoothLimits(tau_decay=0.5, tau_grow=0.1)

        self.fft_plot = self.plot_layout.addPlot(col=0, row=1)
        self.fft_plot.setMenuEnabled(False)
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.setLabel("left", "Displacement (<font>&mu;</font>m)")
        self.fft_plot.setLabel("bottom", "Frequency (Hz)")
        self.fft_plot.setLogMode(False, True)
        self.fft_plot.addItem(pg.PlotDataItem())
        self.fft_curve = [
            self.fft_plot.plot(**feat_kw_blue),
            self.fft_plot.plot(**feat_kw_orange),
            self.fft_plot.plot(**dict(pen=pen_blue, **symbol_dot_kw)),
        ]

        self.text_item_fft = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.text_item_fft.hide()
        self.fft_plot.addItem(self.text_item_fft)

        self.smooth_max_fft = et.utils.SmoothMax()

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        # Extra result
        time_series = processor_result.extra_result.zm_time_series
        lp_displacements_threshold = processor_result.extra_result.lp_displacements_threshold
        amplitude_threshold = processor_result.extra_result.amplitude_threshold

        # Processor result
        lp_displacements = processor_result.lp_displacements
        lp_displacements_freqs = processor_result.lp_displacements_freqs
        max_amplitude = processor_result.max_sweep_amplitude
        max_displacement = processor_result.max_displacement
        max_displacement_freq = processor_result.max_displacement_freq
        time_series_std = processor_result.time_series_std

        # Plot object presence metric
        self.presence_curve.setData([self.meas_dist_m], [max_amplitude])
        self.presence_threshold.setValue(amplitude_threshold)
        lim = self.smooth_max_presence.update(max_amplitude)
        self.object_detection_plot.setYRange(0, max(1000.0, lim))

        # Plot time series
        if time_series is not None and amplitude_threshold < max_amplitude:
            assert time_series_std is not None
            lim = self.smooth_lim_time_series.update(time_series)
            self.time_series_plot.setYRange(lim[0], lim[1])
            self.time_series_plot.setXRange(0, time_series.shape[0])

            self.text_item_time_series.setPos(time_series.size / 2, lim[1] * 0.95)
            time_series_std_str = "{:.0f}".format(time_series_std)
            html_format = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:15pt;">'
                "{}</span></div>".format("STD : " + time_series_std_str + "<font>&mu;</font>m")
            )
            self.text_item_time_series.setHtml(html_format)
            self.text_item_time_series.hide()  # do not display std(for now)
            self.time_series_curve.setData(time_series)

        # Plot spectrum
        if lp_displacements is not None:
            assert time_series is not None
            assert lp_displacements is not None

            self.fft_curve[0].setData(lp_displacements_freqs, lp_displacements)
            self.fft_curve[1].setData(lp_displacements_freqs, lp_displacements_threshold)
            lim = self.smooth_max_fft.update(np.max(lp_displacements))
            self.fft_plot.setYRange(-1, np.log10(lim))

            if max_displacement_freq is not None and max_displacement is not None:
                self.fft_curve[2].setData([max_displacement_freq], [max_displacement])

                # Place text box centered at the top of the plotting window
                self.text_item_fft.setPos(max(lp_displacements_freqs) / 2, np.log10(lim) * 0.95)
                max_displacement_str = "{:.0f}".format(max_displacement)
                max_displacement_freq_str = "{:.1f}".format(max_displacement_freq)
                html_format = (
                    '<div style="text-align: center">'
                    '<span style="color: #FFFFFF;font-size:15pt;">'
                    "{}</span></div>".format(
                        "Frequency: "
                        + max_displacement_freq_str
                        + " Hz"
                        + "<br>"
                        + "Displacement: "
                        + max_displacement_str
                        + "<font>&mu;</font>m"
                    )
                )
                self.text_item_fft.setHtml(html_format)
                self.text_item_fft.show()
            else:
                self.fft_curve[2].setData([], [])
                self.text_item_fft.hide()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


VIBRATION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="vibration",
    title="Vibration measurement",
    docs_link="https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/examples/vibration.html",
    description="Quantify the frequency content of vibrating object.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Low frequency", preset_id=PluginPresetId.LOW_FREQ),
        PluginPresetBase(name="High frequency", preset_id=PluginPresetId.HIGH_FREQ),
    ],
    default_preset_id=PluginPresetId.LOW_FREQ,
)
