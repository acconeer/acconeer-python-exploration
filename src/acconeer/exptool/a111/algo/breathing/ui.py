# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        assert sensor_config.update_rate is not None

        f = sensor_config.update_rate
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.hist_plot_len_s = processing_config.hist_plot_len
        self.hist_plot_len = int(round(self.hist_plot_len_s * f))
        self.move_xs = (np.arange(-self.hist_plot_len, 0) + 1) / f
        self.smooth_max = et.utils.SmoothMax(f, hysteresis=0.4, tau_decay=1.5)

    def setup(self, win):
        win.setWindowTitle("Acconeer breathing example")
        win.resize(800, 600)

        self.env_plot = win.addPlot(title="Amplitude of IQ data and change")
        self.env_plot.setMenuEnabled(False)
        self.env_plot.setMouseEnabled(x=False, y=False)
        self.env_plot.hideButtons()
        self.env_plot.addLegend()
        self.env_plot.showGrid(x=True, y=True)
        self.env_curve = self.env_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Amplitude of IQ data",
        )
        self.delta_curve = self.env_plot.plot(
            pen=et.utils.pg_pen_cycler(1),
            name="Phase change between sweeps",
        )
        self.peak_vline = pg.InfiniteLine(pen=pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine))
        self.env_plot.addItem(self.peak_vline)

        self.peak_plot = win.addPlot(title="Phase of IQ at peak")
        self.peak_plot.setMenuEnabled(False)
        self.peak_plot.setMouseEnabled(x=False, y=False)
        self.peak_plot.hideButtons()
        et.utils.pg_setup_polar_plot(self.peak_plot, 1)
        self.peak_curve = self.peak_plot.plot(pen=et.utils.pg_pen_cycler(0))
        self.peak_scatter = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=15)
        self.peak_plot.addItem(self.peak_scatter)
        self.peak_text_item = pg.TextItem(color=pg.mkColor("k"), anchor=(0, 1))
        self.peak_plot.addItem(self.peak_text_item)
        self.peak_text_item.setPos(-1.15, -1.15)

        win.nextRow()

        self.zoom_plot = win.addPlot(title="Relative movement")
        self.zoom_plot.setMenuEnabled(False)
        self.zoom_plot.setMouseEnabled(x=False, y=False)
        self.zoom_plot.hideButtons()
        self.zoom_plot.showGrid(x=True, y=True)
        self.zoom_plot.setLabel("bottom", "Time (s)")
        self.zoom_plot.setLabel("left", "Movement (mm)")
        self.zoom_curve = self.zoom_plot.plot(pen=et.utils.pg_pen_cycler(0))

        self.move_plot = win.addPlot(title="Breathing movement")
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Time (s)")
        self.move_plot.setLabel("left", "Movement (mm)")
        self.move_plot.setYRange(-2, 2)
        self.move_plot.setXRange(-self.hist_plot_len_s, 0)
        self.move_curve = self.move_plot.plot(pen=et.utils.pg_pen_cycler(0))
        self.move_text_item = pg.TextItem(color=pg.mkColor("k"), anchor=(0, 1))
        self.move_text_item.setPos(self.move_xs[0], -2)
        self.move_plot.addItem(self.move_text_item)

    def update(self, data):
        envelope = data["env_ampl"]
        m = self.smooth_max.update(envelope)
        plot_delta = data["env_delta"] * m * 2e-5 + 0.5 * m

        norm_peak_hist_re = np.real(data["peak_hist"]) / m
        norm_peak_hist_im = np.imag(data["peak_hist"]) / m
        peak_std_text = "Std: {:.3f}mm".format(data["peak_std_mm"])
        peak_x = self.depths[data["peak_idx"]]

        self.env_plot.setYRange(0, m)
        self.env_curve.setData(self.depths, envelope)
        self.delta_curve.setData(self.depths, plot_delta)

        self.peak_scatter.setData([norm_peak_hist_re[0]], [norm_peak_hist_im[0]])
        self.peak_curve.setData(norm_peak_hist_re, norm_peak_hist_im)
        self.peak_text_item.setText(peak_std_text)
        self.peak_vline.setValue(peak_x)

        m = max(2, max(np.abs(data["breathing_history"])))

        self.move_curve.setData(self.move_xs, data["breathing_history"])
        self.move_plot.setYRange(-m, m)
        self.move_text_item.setPos(self.move_xs[0], -m)
        self.zoom_curve.setData(self.move_xs[self.move_xs.size // 2 :], data["zoom_hist"])
        self.move_text_item.setText(data["breathing_text"])
