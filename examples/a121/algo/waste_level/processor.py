# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M, get_distances_m
from acconeer.exptool.a121.algo.waste_level import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_sensor_config,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    processor_config = ProcessorConfig()

    sensor_config = get_sensor_config()

    metadata = client.setup_session(sensor_config)
    client.start_session()

    processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=processor_config,
    )

    pg_updater = PGUpdater(
        metadata=metadata, sensor_config=sensor_config, processor_config=processor_config
    )
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        processor_result = processor.process(result)
        try:
            pg_process.put_data(processor_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.stop_session()
    client.close()


class PGUpdater:
    def __init__(self, metadata, sensor_config, processor_config):
        self.metadata = metadata
        self.sensor_config = sensor_config
        self.processor_config = processor_config

    def setup(self, win) -> None:
        # Phase standard deviation plot
        self.phase_std_plot = self._create_phase_std_plot(win)
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
        threshold_line = pg.InfiniteLine(
            pos=self.processor_config.threshold, angle=0, pen=dashed_pen
        )
        self.phase_std_plot.addItem(threshold_line)

        vertical_line_start = pg.InfiniteLine(
            pos=self.processor_config.bin_start_m,
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
            pos=self.processor_config.bin_end_m,
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

        self.distances_m = get_distances_m(self.sensor_config, self.metadata)
        self.threshold = self.processor_config.threshold
        self.sequence_ones = np.ones(self.processor_config.distance_sequence_n)

        # Level history plot
        self.level_history_plot = self._create_history_plot(win)

        if self.sensor_config.frame_rate is not None:
            history_length_s = 5
            history_length_n = int(round(history_length_s * self.sensor_config.frame_rate))
            self.hist_xs = np.linspace(-history_length_s, 0, history_length_n)
        else:
            history_length_n = 100
            self.hist_xs = np.linspace(-history_length_n, 0, history_length_n)
            self.level_history_plot.setLabel("bottom", "Frame")

        self.level_history = np.full(history_length_n, np.nan)
        self.level_history_plot.setYRange(
            0,
            self.processor_config.bin_end_m
            - np.minimum(
                self.processor_config.bin_start_m,
                self.sensor_config.subsweeps[0].start_point * APPROX_BASE_STEP_LENGTH_M,
            ),
        )

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.level_history_curve = self.level_history_plot.plot(**feat_kw, connect="finite")

        top_bin_horizontal_line = pg.InfiniteLine(
            pos=self.processor_config.bin_end_m - self.processor_config.bin_start_m,
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

        win.addItem(self.rect_plot, row=0, col=0)
        self.win = win

    def update(self, processor_result: ProcessorResult) -> None:
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
        if self.win.width() < 600:
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


if __name__ == "__main__":
    main()
