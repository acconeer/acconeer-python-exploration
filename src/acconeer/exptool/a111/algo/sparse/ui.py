# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from PySide6 import QtGui

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.depth_res = session_info["step_length_m"]
        self.xs = np.tile(self.depths, sensor_config.sweeps_per_frame)
        self.smooth_limits = et.utils.SmoothLimits(sensor_config.update_rate)

    def setup(self, win):
        win.setWindowTitle("Acconeer sparse example")

        # For history images:
        rate = self.sensor_config.update_rate
        xlabel = "Frames" if rate is None else "Time (s)"
        x_scale = 1.0 if rate is None else 1.0 / rate
        y_scale = self.depth_res
        x_offset = -self.processing_config.history_length * x_scale
        y_offset = self.depths[0] - 0.5 * self.depth_res

        self.data_plots = []
        self.scatters = []
        self.data_history_ims = []
        self.presence_history_ims = []

        for i in range(len(self.sensor_config.sensor)):
            data_plot = win.addPlot(title="Sparse data", row=0, col=i)
            data_plot.setMenuEnabled(False)
            data_plot.setMouseEnabled(x=False, y=False)
            data_plot.hideButtons()
            data_plot.showGrid(x=True, y=True)
            data_plot.setLabel("bottom", "Depth (m)")
            data_plot.setLabel("left", "Amplitude")
            scatter = pg.ScatterPlotItem(size=10)
            data_plot.addItem(scatter)

            cmap_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
            cmap = LinearSegmentedColormap.from_list("mycmap", cmap_cols)
            cmap._init()
            lut = (cmap._lut * 255).view(np.ndarray).astype(np.uint8)

            self.data_history_plot = win.addPlot(title="Data history", row=1, col=i)
            self.data_history_plot.setMenuEnabled(False)
            self.data_history_plot.setMouseEnabled(x=False, y=False)
            self.data_history_plot.hideButtons()
            data_history_im = pg.ImageItem(autoDownsample=True)
            data_history_im.setLookupTable(lut)
            self.data_history_plot.addItem(data_history_im)
            self.data_history_plot.setLabel("bottom", xlabel)
            self.data_history_plot.setLabel("left", "Depth (m)")

            self.presence_history_plot = win.addPlot(title="Movement history", row=2, col=i)
            self.presence_history_plot.setMenuEnabled(False)
            self.presence_history_plot.setMouseEnabled(x=False, y=False)
            self.presence_history_plot.hideButtons()
            presence_history_im = pg.ImageItem(autoDownsample=True)
            presence_history_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
            self.presence_history_plot.addItem(presence_history_im)
            self.presence_history_plot.setLabel("bottom", xlabel)
            self.presence_history_plot.setLabel("left", "Depth (m)")

            for im in [presence_history_im, data_history_im]:
                im.resetTransform()
                tr = QtGui.QTransform()
                tr.translate(x_offset, y_offset)
                tr.scale(x_scale, y_scale)
                im.setTransform(tr)

            self.data_plots.append(data_plot)
            self.scatters.append(scatter)
            self.data_history_ims.append(data_history_im)
            self.presence_history_ims.append(presence_history_im)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.presence_history_plot.setVisible(processing_config.show_move_history_plot)
        self.data_history_plot.setVisible(processing_config.show_data_history_plot)

    def update(self, d):
        data_limits = self.smooth_limits.update(d["data"])

        for i in range(len(self.sensor_config.sensor)):
            ys = d["data"][i].flatten()
            self.scatters[i].setData(self.xs, ys)
            self.data_plots[i].setYRange(*data_limits)

            data_history_adj = d["data_history"][:, i] - 2**15
            sign = np.sign(data_history_adj)
            data_history_adj = np.abs(data_history_adj)
            data_history_adj /= data_history_adj.max()
            data_history_adj = np.power(data_history_adj, 1 / 2.2)  # gamma correction
            data_history_adj *= sign
            self.data_history_ims[i].updateImage(data_history_adj, levels=(-1.05, 1.05))

            m = np.max(d["presence_history"][:, i]) * 1.1
            self.presence_history_ims[i].updateImage(d["presence_history"][:, i], levels=(0, m))
