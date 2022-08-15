# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import pyqtgraph as pg

from acconeer.exptool import utils


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.session_info = session_info
        self.smooth_max = utils.SmoothMax(sensor_config.update_rate)

    def setup(self, win):
        num_depths = self.session_info["bin_count"]
        start = self.session_info["range_start_m"]
        length = self.session_info["range_length_m"]
        end = start + length

        xs = np.linspace(start, end, num_depths * 2 + 1)[1::2]
        bin_width = 0.8 * length / num_depths

        self.plot = win.addPlot()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")
        self.plot.setXRange(start, end)
        self.plot.setYRange(0, 1)

        self.bar_graph = pg.BarGraphItem(
            x=xs,
            height=np.zeros_like(xs),
            width=bin_width,
            brush=pg.mkBrush(utils.color_cycler()),
        )

        self.plot.addItem(self.bar_graph)

    def update(self, data):
        self.bar_graph.setOpts(height=data)
        self.plot.setYRange(0, self.smooth_max.update(data))
