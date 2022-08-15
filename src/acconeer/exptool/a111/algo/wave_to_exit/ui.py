# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.history_length_s = processing_config.history_length_s
        self.depths = et.a111.get_range_depths(sensor_config, session_info)

        max_num_of_sectors = max(6, self.depths.size // 3)
        self.sector_size = max(1, -(-self.depths.size // max_num_of_sectors))
        self.num_sectors = -(-self.depths.size // self.sector_size)
        self.sector_offset = (self.num_sectors * self.sector_size - self.depths.size) // 2

        self.setup_is_done = False

        self.show_detect = 0

    def setup(self, win):
        win.setWindowTitle("Acconeer swipe algorithm example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        # Data plot

        self.data_plot = win.addPlot(
            row=0,
            col=0,
            title="Frame movement",
        )
        self.data_plot.setMenuEnabled(False)
        self.data_plot.setMouseEnabled(x=False, y=False)
        self.data_plot.hideButtons()
        self.data_plot.showGrid(x=True, y=True)
        self.data_plot.setLabel("bottom", "Depth (m)")
        self.data_plot.setLabel("left", "Amplitude")
        self.data_plot.setYRange(0, 2**16)
        self.frame_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(0),
        )

        self.data_plot.addItem(self.frame_scatter)
        self.frame_smooth_limits = et.utils.SmoothLimits(self.sensor_config.update_rate)

        # Trigger history plot

        self.move_hist_plot = pg.PlotItem(title="Presence history")
        self.move_hist_plot.setMenuEnabled(False)
        self.move_hist_plot.setMouseEnabled(x=False, y=False)
        self.move_hist_plot.hideButtons()
        self.move_hist_plot.showGrid(x=True, y=True)
        self.move_hist_plot.setLabel("bottom", "Time (s)")
        self.move_hist_plot.setLabel("left", "Score")
        self.move_hist_plot.setXRange(-self.history_length_s, 0)
        self.history_smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)
        self.move_hist_plot.setYRange(0, 10)

        self.move_hist_curve = self.move_hist_plot.plot(pen=et.utils.pg_pen_cycler())
        self.trig_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.cool_line = pg.InfiniteLine(angle=0, pen=dashed_pen)

        self.move_hist_plot.addItem(self.trig_line)
        self.move_hist_plot.addItem(self.cool_line)

        self.present_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>"
        )
        not_present_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("No presence detected")
        )
        self.present_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.not_present_text_item = pg.TextItem(
            html=not_present_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        self.move_hist_plot.addItem(self.present_text_item)
        self.move_hist_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()
        self.not_present_text_item.hide()

        sublayout = win.addLayout(row=3, col=0)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.move_hist_plot, col=0)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.data_plot.setVisible(True)

        self.trig_line.setPos(processing_config.detection_threshold)
        self.cool_line.setPos(processing_config.cool_down_threshold)

    def update(self, data):
        self.frame_scatter.setData(
            np.tile(self.depths, self.sensor_config.sweeps_per_frame),
            data["frame"].flatten(),
        )

        self.data_plot.setYRange(*self.frame_smooth_limits.update(data["frame"]))

        move_hist_ys = data["presence_history"]
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_ys))

        m_hist = max(np.max(move_hist_ys), self.processing_config.detection_threshold * 1.05)
        m_hist = self.history_smooth_max.update(m_hist)

        if self.processing_config.history_plot_ceiling is not None:
            self.move_hist_plot.setYRange(0, self.processing_config.history_plot_ceiling)
            self.move_hist_curve.setData(
                move_hist_xs,
                np.minimum(move_hist_ys, self.processing_config.history_plot_ceiling),
            )
            self.set_present_text_y_pos(self.processing_config.history_plot_ceiling)
        else:
            self.move_hist_plot.setYRange(0, m_hist)
            self.move_hist_curve.setData(move_hist_xs, move_hist_ys)
            self.set_present_text_y_pos(m_hist)

        if any(data["detection_history"][-5:]):
            self.show_detect = 15

        if self.show_detect > 0:
            present_text = "Wave!"
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.show_detect -= 1
        else:
            self.present_text_item.hide()

    def set_present_text_y_pos(self, y):
        self.present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
        self.not_present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
