# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Optional, Type

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorBackendPluginSharedState,
    ProcessorPluginPreset,
    ProcessorViewPluginBase,
    SetupMessage,
)
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M, get_distances_m
from acconeer.exptool.a121.algo.waste_level import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_processor_config,
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
    PLASTIC_WASTE_BIN = auto()


class BackendPlugin(ProcessorBackendPluginBase[ProcessorConfig, ProcessorResult]):
    PLUGIN_PRESETS = {
        PluginPresetId.PLASTIC_WASTE_BIN.value: lambda: ProcessorPluginPreset(
            session_config=a121.SessionConfig(get_sensor_config()),
            processor_config=get_processor_config(),
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
        return {
            "bin_start_m": pidgets.FloatPidgetFactory(
                name_label_text="Bin start:",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "bin_start_m"),
                suffix=" m",
                decimals=3,
                limits=(0.03, 20),
            ),
            "bin_end_m": pidgets.FloatPidgetFactory(
                name_label_text="Bin end:",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "bin_end_m"),
                suffix=" m",
                decimals=3,
                limits=(0.05, 20),
            ),
            "threshold": pidgets.FloatSliderPidgetFactory(
                name_label_text="Threshold:",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "threshold"),
                decimals=1,
                limits=(0.0, 4),
            ),
            "distance_sequence_n": pidgets.IntPidgetFactory(
                name_label_text="Number of distances in sequence:",
                name_label_tooltip=get_attribute_docstring(ProcessorConfig, "distance_sequence_n"),
                limits=(1, 10),
            ),
            "median_filter_length": pidgets.IntPidgetFactory(
                name_label_text="Median filter length:",
                name_label_tooltip=get_attribute_docstring(
                    ProcessorConfig, "median_filter_length"
                ),
                limits=(1, 10),
            ),
        }

    @classmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfig]:
        return ProcessorConfig

    @classmethod
    def supports_multiple_subsweeps(self) -> bool:
        return True


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
                session_config=message.session_config,
                processor_config=message.processor_config,
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

    def setup(
        self,
        metadata: a121.Metadata,
        session_config: a121.SessionConfig,
        processor_config: ProcessorConfig,
    ) -> None:
        self.plot_layout.clear()

        # Phase standard deviation plot
        self.phase_std_plot = self._create_phase_std_plot(self.plot_layout)
        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        self.phase_std_curve = self.phase_std_plot.plot(pen=pen)
        self.phase_std_dots_above = pg.ScatterPlotItem(symbol="o", size=10, brush=brush, pen="k")
        self.phase_std_plot.addItem(self.phase_std_dots_above)
        brush = et.utils.pg_brush_cycler(1)
        self.phase_std_dots_below = pg.ScatterPlotItem(symbol="o", size=10, brush=brush, pen="k")
        self.phase_std_plot.addItem(self.phase_std_dots_below)
        brush = et.utils.pg_brush_cycler(2)
        self.phase_std_dots_detection = pg.ScatterPlotItem(
            symbol="o", size=10, brush=brush, pen="k"
        )
        self.phase_std_plot.addItem(self.phase_std_dots_detection)

        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.PenStyle.DashLine)
        threshold_line = pg.InfiniteLine(pos=processor_config.threshold, angle=0, pen=dashed_pen)
        self.phase_std_plot.addItem(threshold_line)

        vertical_line_start = pg.InfiniteLine(
            pos=processor_config.bin_start_m,
            pen=et.utils.pg_pen_cycler(7),
            label="Bin top",
            labelOpts={
                "position": 0.6,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.phase_std_plot.addItem(vertical_line_start)

        vertical_line_end = pg.InfiniteLine(
            pos=processor_config.bin_end_m,
            pen=et.utils.pg_pen_cycler(7),
            label="Bin bottom",
            labelOpts={
                "position": 0.6,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.phase_std_plot.addItem(vertical_line_end)

        self.level_line = pg.InfiniteLine(
            pen=et.utils.pg_pen_cycler(2),
            label="Fill level",
            labelOpts={
                "position": 0.8,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.phase_std_plot.addItem(self.level_line)
        self.level_line.hide()

        self.distances_m = get_distances_m(session_config.sensor_config, metadata)
        self.threshold = processor_config.threshold
        self.sequence_ones = np.ones(processor_config.distance_sequence_n)

        # Level history plot
        self.level_history_plot = self._create_history_plot(self.plot_layout)

        if session_config.sensor_config.frame_rate is not None:
            history_length_s = 5
            history_length_n = int(
                round(history_length_s * session_config.sensor_config.frame_rate)
            )
            self.hist_xs = np.linspace(-history_length_s, 0, history_length_n)
        elif session_config.update_rate is not None:
            history_length_s = 5
            history_length_n = int(round(history_length_s * session_config.update_rate))
            self.hist_xs = np.linspace(-history_length_s, 0, history_length_n)
        else:
            history_length_n = 100
            self.hist_xs = np.linspace(-history_length_n, 0, history_length_n)
            self.level_history_plot.setLabel("bottom", "Frame")

        self.level_history = np.full(history_length_n, np.nan)
        self.level_history_plot.setYRange(
            0,
            processor_config.bin_end_m
            - np.minimum(
                processor_config.bin_start_m,
                session_config.sensor_config.subsweeps[0].start_point * APPROX_BASE_STEP_LENGTH_M,
            ),
        )

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.level_history_curve = self.level_history_plot.plot(**feat_kw, connect="finite")

        top_bin_horizontal_line = pg.InfiniteLine(
            pos=processor_config.bin_end_m - processor_config.bin_start_m,
            pen=et.utils.pg_pen_cycler(7),
            angle=0,
            label="Bin top",
            labelOpts={
                "position": 0.5,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.level_history_plot.addItem(top_bin_horizontal_line)

        bottom_bin_horizontal_line = pg.InfiniteLine(
            pos=0,
            pen=et.utils.pg_pen_cycler(7),
            angle=0,
            label="Bin bottom",
            labelOpts={
                "position": 0.5,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.level_history_plot.addItem(bottom_bin_horizontal_line)

        # Level plot
        self.num_rects = 16
        self.rect_plot = pg.PlotItem()
        self.rect_plot.setAspectLocked()
        self.rect_plot.hideAxis("left")
        self.rect_plot.hideAxis("bottom")
        self.rects = []

        pen = pg.mkPen(None)
        rect_width = self.num_rects / 2.0
        for r in np.arange(self.num_rects) + 1:
            rect = pg.QtWidgets.QGraphicsRectItem(0, r, rect_width, 1)
            rect.setPen(pen)
            self.rect_plot.addItem(rect)
            self.rects.append(rect)

        self.level_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:12pt;">'
            "{}</span></div>"
        )

        self.level_text_item = pg.TextItem(
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        no_detection_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:12pt;">'
            "{}</span></div>".format("No detection")
        )

        self.no_detection_text_item = pg.TextItem(
            html=no_detection_html,
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )

        self.rect_plot.addItem(self.level_text_item)
        self.rect_plot.addItem(self.no_detection_text_item)
        self.level_text_item.setPos(self.num_rects / 4.0, self.num_rects + 4.0)
        self.level_text_item.hide()
        self.no_detection_text_item.setPos(self.num_rects / 4.0, self.num_rects + 4.0)
        self.no_detection_text_item.show()

        self.plot_layout.addItem(self.rect_plot, row=0, col=0)

    def draw_plot_job(self, processor_result: ProcessorResult) -> None:
        # Phase standard deviation plot
        self.phase_std_curve.setData(self.distances_m, processor_result.extra_result.phase_std)
        if processor_result.extra_result.distance_m is not None:
            self.level_line.setPos(processor_result.extra_result.distance_m)
            self.level_line.show()
        else:
            self.level_line.hide()

        detection_array = processor_result.extra_result.phase_std < self.threshold
        if np.all(detection_array):
            self.phase_std_dots_below.setData(
                self.distances_m, processor_result.extra_result.phase_std
            )
            self.phase_std_dots_above.hide()
            self.phase_std_dots_detection.hide()
        elif np.any(detection_array):
            above_idxs = np.argwhere(~detection_array)
            above_idxs = above_idxs.reshape(above_idxs.shape[0])
            below_idxs = np.argwhere(detection_array)
            below_idxs = below_idxs.reshape(below_idxs.shape[0])
            consecutive_true_indices = np.where(
                np.convolve(detection_array, self.sequence_ones, mode="valid")
                == self.sequence_ones.shape[0]
            )[0]
            detection_idxs = []
            for i in consecutive_true_indices:
                for j in np.arange(i, i + self.sequence_ones.shape[0]):
                    if j not in detection_idxs and j < detection_array.shape[0]:
                        detection_idxs.append(j)

            remove = np.isin(below_idxs, detection_idxs)
            below_idxs = below_idxs[~remove]

            self.phase_std_dots_above.setData(
                self.distances_m[above_idxs], processor_result.extra_result.phase_std[above_idxs]
            )
            self.phase_std_dots_below.setData(
                self.distances_m[below_idxs], processor_result.extra_result.phase_std[below_idxs]
            )
            if len(detection_idxs) > 0:
                self.phase_std_dots_detection.setData(
                    self.distances_m[detection_idxs],
                    processor_result.extra_result.phase_std[detection_idxs],
                )
                self.phase_std_dots_detection.show()
            else:
                self.phase_std_dots_detection.hide()

            self.phase_std_dots_above.show()
            self.phase_std_dots_below.show()
        else:
            self.phase_std_dots_above.setData(
                self.distances_m, processor_result.extra_result.phase_std
            )
            self.phase_std_dots_below.hide()
            self.phase_std_dots_detection.hide()

        # History plot

        self.level_history = np.roll(self.level_history, -1)
        if processor_result.level_m is not None:
            self.level_history[-1] = processor_result.level_m
        else:
            self.level_history[-1] = np.nan

        if np.all(np.isnan(self.level_history)):
            self.level_history_curve.hide()
        else:
            self.level_history_curve.setData(self.hist_xs, self.level_history)
            self.level_history_curve.show()

        # Level plot

        # Show the percentage level plot if the plot width is greater than 600 pixels,
        # otherwise display the level as text.
        if self.plot_layout.width() < 600:
            if processor_result.level_percent is None:
                self.level_text_item.hide()
                self.no_detection_text_item.show()
            elif processor_result.level_percent > 100:  # Overflow
                level_text = "Overflow"
                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.show()
                self.no_detection_text_item.hide()
            elif processor_result.level_percent > 0:  # In bin detection
                assert processor_result.level_m is not None
                assert processor_result.level_percent is not None
                level_text = "Level: {:.2f} m, {:.0f} %".format(
                    processor_result.level_m,
                    processor_result.level_percent,
                )
                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.show()
                self.no_detection_text_item.hide()
            else:  # No detection
                self.level_text_item.hide()
                self.no_detection_text_item.show()

            for rect in self.rects:
                rect.setVisible(False)
        else:
            if processor_result.level_percent is None:  # No detection
                level_text = "No detection"
                for rect in self.rects:
                    rect.setBrush(et.utils.pg_brush_cycler(7))
                self.level_text_item.hide()
                self.no_detection_text_item.show()
            elif processor_result.level_percent > 100:  # Overflow
                for rect in self.rects:
                    rect.setBrush(et.utils.pg_brush_cycler(0))

                level_text = "Overflow"
                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.show()
                self.no_detection_text_item.hide()
            else:  # In bin detection
                self.bar_loc = int(
                    np.around(processor_result.level_percent / 100 * self.num_rects)
                )
                for rect in self.rects[: self.bar_loc]:
                    rect.setBrush(et.utils.pg_brush_cycler(0))

                for rect in self.rects[self.bar_loc :]:
                    rect.setBrush(et.utils.pg_brush_cycler(7))

                assert processor_result.level_m is not None
                assert processor_result.level_percent is not None
                level_text = "Level: {:.2f} m, {:.0f} %".format(
                    processor_result.level_m,
                    processor_result.level_percent,
                )
                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.show()
                self.no_detection_text_item.hide()

            for rect in self.rects:
                rect.setVisible(True)

    @staticmethod
    def _create_phase_std_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        phase_std_plot = parent.addPlot(row=1, col=0, colspan=3)
        phase_std_plot.setTitle("Phase standard deviation")
        phase_std_plot.setLabel(axis="bottom", text="Distance [m]")
        phase_std_plot.setLabel("left", "Phase std")
        phase_std_plot.setMenuEnabled(False)
        phase_std_plot.setMouseEnabled(x=False, y=False)
        phase_std_plot.hideButtons()
        phase_std_plot.showGrid(x=True, y=True, alpha=0.5)
        phase_std_plot.setYRange(0, 4)

        return phase_std_plot

    @staticmethod
    def _create_history_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        history_plot = parent.addPlot(row=0, col=1, colspan=2)
        history_plot.setTitle("Level history")
        history_plot.setMenuEnabled(False)
        history_plot.showGrid(x=True, y=True)
        history_plot.setLabel("left", "Estimated level (m)")
        history_plot.setLabel("bottom", "Time (s)")

        return history_plot


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        return PlotPlugin(app_model=app_model)


WASTE_LEVEL_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="waste_level",
    title="Waste level",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/waste_level.html",
    description="Detect waste level in a bin.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(
            name="Plastic waste bin",
            description="Settings for measuring waste level in a plastic waste bin (240 liter)",
            preset_id=PluginPresetId.PLASTIC_WASTE_BIN,
        ),
    ],
    default_preset_id=PluginPresetId.PLASTIC_WASTE_BIN,
)
