# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et

from .constants import HISTORY_LENGTH_S


INIT_Y_RANGE = 500000


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.processing_config = processing_config

    def setup(self, win):
        win.setWindowTitle("Acconeer button press sparse example")

        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.calibrated_text_vis_age = 0

        self.signal_hist_plot = win.addPlot(title="Signal history")
        self.signal_hist_plot.setMenuEnabled(False)
        self.signal_hist_plot.setMouseEnabled(x=False, y=False)
        self.signal_hist_plot.addLegend()
        self.signal_hist_plot.hideButtons()
        self.signal_hist_plot.showGrid(x=True, y=True)
        self.signal_hist_plot.setLabel("bottom", "Time (s)")
        self.signal_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.signal_hist_plot.setYRange(0, 2**15)

        self.signal_hist_curve = self.signal_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Signal",
        )
        self.average_hist_curve = self.signal_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Low pass filtered signal",
        )

        win.nextRow()

        self.proc_plot = win.addPlot(title="Processing history")
        self.proc_plot.setMenuEnabled(False)
        self.proc_plot.setMouseEnabled(x=False, y=False)
        self.proc_plot.hideButtons()
        self.proc_plot.showGrid(x=True, y=True)
        self.proc_plot.setLabel("bottom", "Trigger variable values")
        self.proc_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.proc_plot.setYRange(0, INIT_Y_RANGE)

        self.trig_hist_curve = self.proc_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Trig value",
        )

        self.cool_down_hist_curve = self.proc_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Cool down value",
        )

        self.detection_dots = self.proc_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=20,
            symbolBrush=et.utils.color_cycler(2),
            name="Detections",
        )

        self.limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.proc_plot.addItem(self.limit_line)

        self.smooth_limits = et.utils.SmoothLimits(
            self.sensor_config.update_rate, hysteresis=0.1, tau_decay=3, tau_grow=1
        )

        self.smooth_max_proc = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=3,
        )

        self.calibration_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        calibration_html = self.calibration_html_format.format("Calibrated!")
        self.calibration_text_item = pg.TextItem(
            html=calibration_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.calibration_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * INIT_Y_RANGE)
        self.proc_plot.addItem(self.calibration_text_item)
        self.calibration_text_item.hide()

    def update(self, data):

        signal_hist_ys = data["signal_history"]
        average_hist_ys = data["average_history"]
        cool_down_hist_ys = data["cool_down_history"]
        trig_hist_ys = data["trig_history"]
        t_detections = data["detection_history"]
        calibrated = data["calibrated"]
        hist_xs = np.linspace(-HISTORY_LENGTH_S, 0, len(signal_hist_ys))

        self.signal_hist_curve.setData(hist_xs, signal_hist_ys)
        self.average_hist_curve.setData(hist_xs, average_hist_ys)

        self.trig_hist_curve.setData(hist_xs, trig_hist_ys)
        self.cool_down_hist_curve.setData(hist_xs, cool_down_hist_ys)

        self.detection_dots.setData(t_detections, data["threshold"] * np.ones(len(t_detections)))
        self.limit_line.setPos(data["threshold"])

        limits = self.smooth_limits.update(signal_hist_ys)

        m = 2 * data["threshold"]
        ymax = self.smooth_max_proc.update(m)

        self.signal_hist_plot.setYRange(limits[0], limits[1])
        self.proc_plot.setYRange(0, ymax)

        self.calibration_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * ymax)

        if calibrated:
            self.calibrated_text_vis_age = len(data["signal_history"]) / 10

        if self.calibrated_text_vis_age > 0:
            self.calibration_text_item.setVisible(True)
            self.calibrated_text_vis_age -= 1
        else:
            self.calibration_text_item.setVisible(False)
