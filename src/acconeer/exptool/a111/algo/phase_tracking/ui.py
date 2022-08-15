# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.smooth_max = et.utils.SmoothMax(sensor_config.update_rate)

    def setup(self, win):
        win.resize(800, 600)
        win.setWindowTitle("Acconeer phase tracking example")

        self.abs_plot = win.addPlot(row=0, col=0)
        self.abs_plot.setMenuEnabled(False)
        self.abs_plot.setMouseEnabled(x=False, y=False)
        self.abs_plot.hideButtons()
        self.abs_plot.showGrid(x=True, y=True)
        self.abs_plot.setLabel("left", "Amplitude")
        self.abs_plot.setLabel("bottom", "Depth (m)")
        self.abs_curve = self.abs_plot.plot(pen=et.utils.pg_pen_cycler(0))
        pen = et.utils.pg_pen_cycler(1)
        pen.setStyle(QtCore.Qt.DashLine)
        self.abs_inf_line = pg.InfiniteLine(pen=pen)
        self.abs_plot.addItem(self.abs_inf_line)

        self.arg_plot = win.addPlot(row=1, col=0)
        self.arg_plot.setMenuEnabled(False)
        self.arg_plot.setMouseEnabled(x=False, y=False)
        self.arg_plot.hideButtons()
        self.arg_plot.showGrid(x=True, y=True)
        self.arg_plot.setLabel("bottom", "Depth (m)")
        self.arg_plot.setLabel("left", "Phase")
        self.arg_plot.setYRange(-np.pi, np.pi)
        self.arg_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)
        self.arg_curve = self.arg_plot.plot(pen=et.utils.pg_pen_cycler())
        self.arg_inf_line = pg.InfiniteLine(pen=pen)
        self.arg_plot.addItem(self.arg_inf_line)

        self.iq_plot = win.addPlot(row=1, col=1, title="IQ at line")
        self.iq_plot.setMenuEnabled(False)
        self.iq_plot.setMouseEnabled(x=False, y=False)
        self.iq_plot.hideButtons()
        et.utils.pg_setup_polar_plot(self.iq_plot, 1)
        self.iq_curve = self.iq_plot.plot(pen=et.utils.pg_pen_cycler())
        self.iq_scatter = pg.ScatterPlotItem(brush=pg.mkBrush(et.utils.color_cycler()), size=15)
        self.iq_plot.addItem(self.iq_scatter)

        self.hist_plot = win.addPlot(row=0, col=1, colspan=2)
        self.hist_plot.setMenuEnabled(False)
        self.hist_plot.setMouseEnabled(x=False, y=False)
        self.hist_plot.hideButtons()
        self.hist_plot.showGrid(x=True, y=True)
        self.hist_plot.setLabel("bottom", "Time (s)")
        self.hist_plot.setLabel("left", "Tracking (mm)")
        self.hist_curve = self.hist_plot.plot(pen=et.utils.pg_pen_cycler())
        self.hist_plot.setYRange(-5, 5)

        self.hist_zoom_plot = win.addPlot(row=1, col=2)
        self.hist_zoom_plot.setMenuEnabled(False)
        self.hist_zoom_plot.setMouseEnabled(x=False, y=False)
        self.hist_zoom_plot.hideButtons()
        self.hist_zoom_plot.showGrid(x=True, y=True)
        self.hist_zoom_plot.setLabel("bottom", "Time (s)")
        self.hist_zoom_plot.setLabel("left", "Tracking (mm)")
        self.hist_zoom_curve = self.hist_zoom_plot.plot(pen=et.utils.pg_pen_cycler())
        self.hist_zoom_plot.setYRange(-0.5, 0.5)

        self.first = True

    def update(self, data):
        if self.first:
            self.ts = np.linspace(-3, 0, len(data["hist_pos"]))
            self.ts_zoom = np.linspace(-1.5, 0, len(data["hist_pos_zoom"]))
            self.first = False

        com_x = (1 - data["com"]) * self.depths[0] + data["com"] * self.depths[-1]
        m = self.smooth_max.update(data["abs"])

        self.abs_curve.setData(self.depths, data["abs"])
        self.abs_plot.setYRange(0, m)
        self.abs_inf_line.setValue(com_x)
        self.arg_curve.setData(self.depths, data["arg"])
        self.arg_inf_line.setValue(com_x)
        self.hist_curve.setData(self.ts, data["hist_pos"])
        self.hist_zoom_curve.setData(self.ts_zoom, data["hist_pos_zoom"])

        norm_iq_val = data["iq_val"] / m
        self.iq_curve.setData([0, np.real(norm_iq_val)], [0, np.imag(norm_iq_val)])
        self.iq_scatter.setData([np.real(norm_iq_val)], [np.imag(norm_iq_val)])
