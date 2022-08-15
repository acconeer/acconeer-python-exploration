# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtGui

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.f = sensor_config.update_rate
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.downsampling_factor = sensor_config.downsampling_factor
        self.step_length = session_info["step_length_m"]

        self.td_smooth_lims = et.utils.SmoothLimits()
        self.collapsed_smooth_max = et.utils.SmoothMax(
            tau_grow=0.1,
        )

        self.setup_is_done = False

    def setup(self, win):
        self.td_plot = win.addPlot(row=0, col=0, title="PSD input data")
        self.td_plot.setMenuEnabled(False)
        self.td_plot.setMouseEnabled(x=False, y=False)
        self.td_plot.hideButtons()
        self.td_plot.addLegend()
        self.td_curves = []
        for i, depth in enumerate(self.depths):
            name = "{:.0f} cm".format(depth * 100)
            curve = self.td_plot.plot(pen=et.utils.pg_pen_cycler(i), name=name)
            self.td_curves.append(curve)

        self.collapsed_plot = win.addPlot(row=1, col=0, title="Collapsed sqrt(PSD)")
        self.collapsed_plot.setMenuEnabled(False)
        self.collapsed_plot.setMouseEnabled(x=False, y=False)
        self.collapsed_plot.hideButtons()
        self.collapsed_plot.setXRange(0, 1)
        self.collapsed_curve = self.collapsed_plot.plot(pen=et.utils.pg_pen_cycler())
        self.collapsed_vline = pg.InfiniteLine(pen=et.utils.pg_pen_cycler())
        self.collapsed_vline.hide()
        self.collapsed_plot.addItem(self.collapsed_vline)

        bg = pg.mkColor(0xFF, 0xFF, 0xFF, 150)
        self.collapsed_text = pg.TextItem(anchor=(0, 1), color="k", fill=bg)
        self.collapsed_text.setPos(0, 0)
        self.collapsed_text.setZValue(100)
        self.collapsed_plot.addItem(self.collapsed_text, ignoreBounds=True)

        self.collapsed_history_plot = win.addPlot(
            row=2, col=0, title="Collapsed sqrt(PSD) history"
        )
        self.collapsed_history_plot.setMenuEnabled(False)
        self.collapsed_history_plot.setMouseEnabled(x=False, y=False)
        self.collapsed_history_plot.hideButtons()
        self.collapsed_history_im = pg.ImageItem()
        self.collapsed_history_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        self.collapsed_history_plot.addItem(self.collapsed_history_im)

        self.dw_plot = win.addPlot(row=3, col=0, title="Depthwise PSD")
        self.dw_plot.setMenuEnabled(False)
        self.dw_plot.setMouseEnabled(x=False, y=False)
        self.dw_plot.hideButtons()
        self.dw_im = pg.ImageItem()
        self.dw_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        self.dw_plot.addItem(self.dw_im)
        self.dw_plot.setLabel("bottom", "Depth (cm)")
        self.dw_plot.getAxis("bottom").setTickSpacing(6 * self.downsampling_factor, 6)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.td_plot.setVisible(processing_config.show_time_domain)
        self.collapsed_history_plot.setVisible(processing_config.show_spect_history)
        self.dw_plot.setVisible(processing_config.show_depthwise_spect)

        lbl = "Time (s)" if self.f else "Frame index"
        self.td_plot.setLabel("bottom", lbl)

        lbl = "Frequency (Hz)" if self.f else "Frequency bin"
        self.collapsed_plot.setLabel("bottom", lbl)

        for plot in [self.dw_plot, self.collapsed_history_plot]:
            plot.setLabel("left", lbl)

        if self.f:
            f_res = self.f / self.processing_config._window_size
        else:
            f_res = 1

        tr = QtGui.QTransform()
        tr.translate(100 * (self.depths[0] - self.step_length / 2), 0)
        tr.scale(100 * self.step_length, f_res)
        self.dw_im.setTransform(tr)

        self.collapsed_history_im.resetTransform()
        tr.translate(0, f_res / 2)
        tr.scale(-1, f_res)
        self.collapsed_history_im.setTransform(tr)

    def update(self, d):
        x = d["ts"]
        for i, curve in enumerate(self.td_curves):
            y = d["sweep_history"][:, i]
            curve.setData(x, y)

        r = self.td_smooth_lims.update(d["sweep_history"])
        self.td_plot.setYRange(*r)

        x = d["fs"]
        y = d["collapsed_asd"]
        self.collapsed_curve.setData(x, y)
        m = self.collapsed_smooth_max.update(y)
        self.collapsed_plot.setXRange(0, x[-1])
        self.collapsed_plot.setYRange(0, m)

        f_max = x[y.argmax()]
        self.collapsed_vline.setPos(f_max)
        self.collapsed_vline.show()

        if self.f:
            s = "Peak: {:5.1f} Hz".format(f_max)
        else:
            s = "Peak: {:3.0f}".format(f_max)
        self.collapsed_text.setText(s)

        im = self.collapsed_history_im
        y = d["collapsed_asd_history"]
        im.updateImage(y[::-1], levels=(0, 1.05 * y.max()))

        y = d["dw_asd"]
        m = max(1, np.max(y)) * 1.05
        self.dw_im.updateImage(y, levels=(0, m))
