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

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        # Data plot

        self.data_plot = win.addPlot(
            row=0,
            col=0,
            title="Frame (blue), fast (orange), and slow (green)",
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
        self.fast_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.slow_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(2),
        )
        self.data_plot.addItem(self.frame_scatter)
        self.data_plot.addItem(self.fast_scatter)
        self.data_plot.addItem(self.slow_scatter)
        self.frame_smooth_limits = et.utils.SmoothLimits(self.sensor_config.update_rate)

        # Noise estimation plot

        self.noise_plot = win.addPlot(
            row=1,
            col=0,
            title="Noise",
        )
        self.noise_plot.setMenuEnabled(False)
        self.noise_plot.setMouseEnabled(x=False, y=False)
        self.noise_plot.hideButtons()
        self.noise_plot.showGrid(x=True, y=True)
        self.noise_plot.setLabel("bottom", "Depth (m)")
        self.noise_plot.setLabel("left", "Amplitude")
        self.noise_curve = self.noise_plot.plot(pen=et.utils.pg_pen_cycler())
        self.noise_smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)

        # Depthwise presence plot

        self.move_plot = win.addPlot(
            row=2,
            col=0,
            title="Depthwise presence",
        )
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Depth (m)")
        self.move_plot.setLabel("left", "Norm. ampl.")
        zero_curve = self.move_plot.plot(self.depths, np.zeros_like(self.depths))
        self.inter_curve = self.move_plot.plot()
        self.total_curve = self.move_plot.plot()
        self.move_smooth_max = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )

        self.move_depth_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        fbi = pg.FillBetweenItem(
            zero_curve,
            self.inter_curve,
            brush=et.utils.pg_brush_cycler(0),
        )
        self.move_plot.addItem(fbi)

        fbi = pg.FillBetweenItem(
            self.inter_curve,
            self.total_curve,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.move_plot.addItem(fbi)

        # Presence history plot

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
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.move_hist_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

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

        # Sector plot

        self.sector_plot = pg.PlotItem()
        self.sector_plot.setAspectLocked()
        self.sector_plot.hideAxis("left")
        self.sector_plot.hideAxis("bottom")
        self.sectors = []

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(self.num_sectors) + 1):
            sector = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            self.sector_plot.addItem(sector)
            self.sectors.append(sector)

        self.sectors.reverse()

        sublayout = win.addLayout(row=3, col=0)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.move_hist_plot, col=0)
        sublayout.addItem(self.sector_plot, col=1)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.data_plot.setVisible(self.processing_config.show_data)
        self.noise_plot.setVisible(self.processing_config.show_noise)
        self.move_plot.setVisible(self.processing_config.show_depthwise_output)
        self.sector_plot.setVisible(self.processing_config.show_sectors)

        for line in self.limit_lines:
            line.setPos(processing_config.detection_threshold)

    def update(self, data):
        self.frame_scatter.setData(
            np.tile(self.depths, self.sensor_config.sweeps_per_frame),
            data["frame"].flatten(),
        )

        self.fast_scatter.setData(self.depths, data["fast"])
        self.slow_scatter.setData(self.depths, data["slow"])
        self.data_plot.setYRange(*self.frame_smooth_limits.update(data["frame"]))

        noise = data["noise"]
        self.noise_curve.setData(self.depths, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(noise))

        movement_x = data["presence_distance"]

        move_ys = data["depthwise_presence"]
        self.inter_curve.setData(self.depths, data["inter"])
        self.total_curve.setData(self.depths, move_ys)
        m = self.move_smooth_max.update(np.max(move_ys))
        m = max(m, 2 * self.processing_config.detection_threshold)
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(bool(data["presence_detected"]))

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

        if data["presence_detected"]:
            present_text = "Presence detected at {:.0f} cm".format(movement_x * 100)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()

        brush = et.utils.pg_brush_cycler(0)
        for sector in self.sectors:
            sector.setBrush(brush)

        if data["presence_detected"]:
            index = (data["presence_distance_index"] + self.sector_offset) // self.sector_size
            self.sectors[index].setBrush(et.utils.pg_brush_cycler(1))

    def set_present_text_y_pos(self, y):
        self.present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
        self.not_present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
