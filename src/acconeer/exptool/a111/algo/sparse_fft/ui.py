# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtGui

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.processing_config = processing_config

        self.downsampling_factor = sensor_config.downsampling_factor
        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        sweep_rate = session_info["sweep_rate"]
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.step_length = session_info["step_length_m"]
        self.f_res = sweep_rate / self.sweeps_per_frame
        self.fft_x_scale = 100 * self.step_length

        self.smooth_max = et.utils.SmoothMax(
            sweep_rate / self.sweeps_per_frame,
            tau_grow=0,
            tau_decay=0.5,
            hysteresis=0.1,
        )

        self.setup_is_done = False

    def setup(self, win):
        self.plots = []
        self.curves = []

        self.layout = win.layout
        self.layout.setRowStretchFactor(0, 2)
        self.layout.setRowStretchFactor(1, 3)
        self.layout.setVerticalSpacing(50)

        for i in range(self.depths.size):
            title = "{:.0f} cm".format(100 * self.depths[i])
            plot = win.addPlot(row=0, col=i, title=title)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()
            plot.setYRange(0, 2**16)
            plot.hideAxis("left")

            if self.depths.size < 8:
                plot.getAxis("bottom").setStyle(stopAxisAtTick=(True, True))
                plot.getAxis("bottom").setTicks(
                    [
                        [
                            (0, "1"),
                            (self.sweeps_per_frame - 1, str(self.sweeps_per_frame)),
                        ],
                    ]
                )
                plot.setLabel("bottom", "Sweep Index")
            else:
                plot.hideAxis("bottom")

            plot.plot(np.arange(self.sweeps_per_frame), 2**15 * np.ones(self.sweeps_per_frame))
            curve = plot.plot(pen=et.utils.pg_pen_cycler())
            self.plots.append(plot)
            self.curves.append(curve)

        self.ft_plot = win.addPlot(row=1, col=0, colspan=self.depths.size)
        self.ft_plot.setMenuEnabled(False)
        self.ft_plot.setMouseEnabled(x=False, y=False)
        self.ft_plot.hideButtons()
        self.ft_im = pg.ImageItem(autoDownsample=True)
        self.ft_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        self.ft_plot.addItem(self.ft_im)
        self.ft_plot.setLabel("bottom", "Depth (cm)")
        self.ft_plot.getAxis("bottom").setTickSpacing(6 * self.downsampling_factor, 6)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        for plot in self.plots:
            plot.setVisible(self.processing_config.show_data_plot)

        if self.processing_config.show_data_plot is False:
            self.layout.setRowStretchFactor(0, 0)
            self.layout.setRowStretchFactor(1, 1)
            self.layout.setVerticalSpacing(0)

        else:
            self.layout.setRowStretchFactor(0, 2)
            self.layout.setRowStretchFactor(1, 3)
            self.layout.setVerticalSpacing(50)

        half_wavelength = 2.445e-3
        self.ft_im.resetTransform()
        tr = QtGui.QTransform()
        tr.translate(100 * (self.depths[0] - self.step_length / 2), 0)
        if self.processing_config.show_speed_plot:
            self.ft_plot.setLabel("left", "Speed (m/s)")
            tr.scale(self.fft_x_scale, self.f_res * half_wavelength)
        else:
            self.ft_plot.setLabel("left", "Frequency (kHz)")
            tr.scale(self.fft_x_scale, self.f_res * 1e-3)

        self.ft_im.setTransform(tr)

    def update(self, data):
        frame = data["frame"]

        for i, ys in enumerate(frame.T):
            self.curves[i].setData(ys)

        m = np.max(data["abs_fft"])
        m = max(m, 1e4)
        m = self.smooth_max.update(m)
        self.ft_im.updateImage(data["abs_fft"], levels=(0, m * 1.05))
