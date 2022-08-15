# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et

from .constants import HISTORY_LENGTH_S


OUTPUT_MAX_SIGNAL = 20000
OUTPUT_MAX_REL_DEV = 0.5
DETECTION_SHOW_S = 2


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        assert sensor_config.update_rate is not None

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer Button Press Example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        self.sign_hist_plot = win.addPlot(title="Signal history")
        self.sign_hist_plot.setMenuEnabled(False)
        self.sign_hist_plot.setMouseEnabled(x=False, y=False)
        self.sign_hist_plot.hideButtons()
        self.sign_hist_plot.addLegend()
        self.sign_hist_plot.showGrid(x=True, y=True)
        self.sign_hist_plot.setLabel("bottom", "Time (s)")
        self.sign_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.sign_hist_plot.setYRange(0, OUTPUT_MAX_SIGNAL)
        self.sign_hist_curve = self.sign_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Envelope signal",
        )
        self.sign_lp_hist_curve = self.sign_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Filtered envelope signal",
        )

        win.nextRow()

        self.rel_dev_hist_plot = win.addPlot(title="Relative deviation history")
        self.rel_dev_hist_plot.setMenuEnabled(False)
        self.rel_dev_hist_plot.setMouseEnabled(x=False, y=False)
        self.rel_dev_hist_plot.hideButtons()
        self.rel_dev_hist_plot.showGrid(x=True, y=True)
        self.rel_dev_hist_plot.setLabel("bottom", "Time (s)")
        self.rel_dev_hist_plot.setXRange(-HISTORY_LENGTH_S, 0)
        self.rel_dev_hist_plot.setYRange(0, OUTPUT_MAX_REL_DEV)
        self.rel_dev_lp_hist_curve = self.rel_dev_hist_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Relative deviation",
        )

        self.detection_dots = self.rel_dev_hist_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=20,
            symbolBrush=et.utils.color_cycler(1),
            name="Detections",
        )

        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.rel_dev_hist_plot.addItem(limit_line)

        self.limit_lines.append(limit_line)

        self.detection_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        detection_html = self.detection_html_format.format("Button press detected!")

        self.detection_text_item = pg.TextItem(
            html=detection_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.detection_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * OUTPUT_MAX_REL_DEV)
        self.rel_dev_hist_plot.addItem(self.detection_text_item)
        self.detection_text_item.hide()

        self.smooth_max_signal = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=3,
        )

        self.smooth_max_rel_dev = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=3,
        )

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.sign_hist_plot.setVisible(True)
        self.rel_dev_hist_plot.setVisible(True)

        for line in self.limit_lines:
            line.setPos(processing_config.threshold)

    def update(self, data):
        signal_hist_ys = data["signal_history"]
        signal_lp_hist_ys = data["signal_lp_history"]
        rel_dev_lp_hist_ys = data["rel_dev_lp_history"]
        t_detections = data["detection_history"]

        hist_xs = np.linspace(-HISTORY_LENGTH_S, 0, len(signal_hist_ys))

        self.sign_hist_curve.setData(hist_xs, signal_hist_ys)
        self.sign_lp_hist_curve.setData(hist_xs, signal_lp_hist_ys)
        self.rel_dev_lp_hist_curve.setData(hist_xs, rel_dev_lp_hist_ys)
        self.detection_dots.setData(t_detections, data["threshold"] * np.ones(len(t_detections)))

        m = np.max(signal_hist_ys) if signal_hist_ys.size > 0 else 1
        self.sign_hist_plot.setYRange(0, self.smooth_max_signal.update(m))

        m = np.max(rel_dev_lp_hist_ys) if rel_dev_lp_hist_ys.size > 0 else 1e-3
        m = max(2 * data["threshold"], m)
        ymax = self.smooth_max_rel_dev.update(m)
        self.rel_dev_hist_plot.setYRange(0, ymax)
        self.detection_text_item.setPos(-HISTORY_LENGTH_S / 2, 0.95 * ymax)

        show_detection_text = t_detections.size > 0 and (-t_detections[-1]) < DETECTION_SHOW_S
        self.detection_text_item.setVisible(bool(show_detection_text))
