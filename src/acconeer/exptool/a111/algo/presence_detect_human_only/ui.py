# Copyright (c) Acconeer AB, 2023
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
        self.latest_fpos = 0
        self.latest_fneg = 0

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
        self.data_plot.setLabel("bottom", "Distance (m)")
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

        # Fast motion plot

        self.fast_plot = win.addPlot(
            row=1,
            col=0,
            title="Fast motion score",
        )
        self.fast_plot.setMenuEnabled(False)
        self.fast_plot.setMouseEnabled(x=False, y=False)
        self.fast_plot.hideButtons()
        self.fast_plot.showGrid(x=True, y=True)
        self.fast_plot.setLabel("bottom", "Distance (m)")
        self.fast_plot.setLabel("left", "Norm. ampl.")
        self.fast_curve = self.fast_plot.plot()
        self.fast_smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)
        zero_curve = self.fast_plot.plot(self.depths, np.zeros_like(self.depths))
        self.fast_smooth_max = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )
        fbi = pg.FillBetweenItem(
            zero_curve,
            self.fast_curve,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.fast_plot.addItem(fbi)
        limit_line = pg.InfiniteLine(angle=0, pen=dashed_pen)
        self.fast_plot.addItem(limit_line)
        self.limit_lines.append(limit_line)

        self.move_depth_line_fast = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line_fast.hide()
        self.fast_plot.addItem(self.move_depth_line_fast)

        # Slow motion plot

        self.slow_plot = win.addPlot(
            row=2,
            col=0,
            title="Slow motion score",
        )
        self.slow_plot.setMenuEnabled(False)
        self.slow_plot.setMouseEnabled(x=False, y=False)
        self.slow_plot.hideButtons()
        self.slow_plot.showGrid(x=True, y=True)
        self.slow_plot.setLabel("bottom", "Distance (m)")
        self.slow_plot.setLabel("left", "Norm. ampl.")
        cal_implementation_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Adapting Threshold . . .")
        )
        self.cal_implementation_item = pg.TextItem(
            html=cal_implementation_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )
        zero_curve = self.slow_plot.plot(self.depths, np.zeros_like(self.depths))
        self.slow_curve = self.slow_plot.plot()
        self.threshold_curve = self.slow_plot.plot(pen=dashed_pen)
        self.slow_smooth_max = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )

        self.move_depth_line_slow = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line_slow.hide()
        self.slow_plot.addItem(self.move_depth_line_slow)
        fbi = pg.FillBetweenItem(
            zero_curve,
            self.slow_curve,
            brush=et.utils.pg_brush_cycler(0),
        )
        self.slow_plot.addItem(fbi)

        self.scatter_oject_curve = pg.ScatterPlotItem(
            size=15,
            brush=et.utils.pg_brush_cycler(3),
        )
        self.slow_plot.addItem(self.scatter_oject_curve)
        self.slow_plot.addItem(self.cal_implementation_item)
        self.cal_implementation_item.hide()

        # Presence history plot

        self.move_hist_plot = pg.PlotItem(title="Detection history")
        self.move_hist_plot.setMenuEnabled(False)
        self.move_hist_plot.setMouseEnabled(x=False, y=False)
        self.move_hist_plot.hideButtons()
        self.move_hist_plot.showGrid(x=True, y=True)
        self.move_hist_plot.setLabel("bottom", "Time (s)")
        self.move_hist_plot.setLabel("left", "Detection")
        self.move_hist_plot.getAxis("left").setTicks([[(0, "False"), (1, "True")]])
        self.move_hist_plot.setXRange(-self.history_length_s, 0)
        self.history_smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)
        self.move_hist_plot.setYRange(-0.1, 2)
        self.fneg_text_item = pg.TextItem(color="black", anchor=(0.5, 0))
        self.fpos_text_item = pg.TextItem(color="black", anchor=(0.5, 0))
        self.move_hist_slow_curve = self.move_hist_plot.plot(pen=et.utils.pg_pen_cycler())
        self.move_hist_fast_curve = self.move_hist_plot.plot(pen=et.utils.pg_pen_cycler(1))
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
        self.move_hist_plot.addItem(self.fneg_text_item)
        self.move_hist_plot.addItem(self.fpos_text_item)
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
        self.fast_plot.setVisible(self.processing_config.show_fast)
        self.slow_plot.setVisible(self.processing_config.show_slow)
        self.sector_plot.setVisible(self.processing_config.show_sectors)

        for line in self.limit_lines:
            line.setPos(processing_config.fast_motion_threshold)

    def update(self, data):
        self.frame_scatter.setData(
            np.tile(self.depths, self.sensor_config.sweeps_per_frame),
            data["frame"].flatten(),
        )

        self.fast_scatter.setData(self.depths, data["fast"])
        self.slow_scatter.setData(self.depths, data["slow"])
        self.data_plot.setYRange(*self.frame_smooth_limits.update(data["frame"]))

        fast = data["fast_motion"]
        self.fast_curve.setData(self.depths, fast)
        m_fast = self.fast_smooth_max.update(np.max(fast))
        m_fast = max(m_fast, 2 * self.processing_config.fast_motion_threshold)
        self.fast_plot.setYRange(0, m_fast)

        slow = data["slow_motion"]
        self.slow_curve.setData(self.depths, slow)
        m_slow = self.slow_smooth_max.update(np.max(slow))
        m_slow = max(m_slow, 2 * self.processing_config.slow_motion_threshold)
        self.slow_plot.setYRange(0, m_slow)
        threshold_array = data["threshold_array"]
        index_threshold_array = np.nonzero(
            [
                threshold_array
                > np.percentile([np.min(threshold_array), np.max(threshold_array)], 30)
            ]
        )
        self.depths_scatter_object = [self.depths[itx] for itx in list(index_threshold_array[1])]
        self.scatter_object = np.ones(len(self.depths_scatter_object)) * 0.5
        self.scatter_oject_curve.setData(self.depths_scatter_object, self.scatter_object)
        index_dps = np.argmax(slow)
        index_array_based = int(index_dps) == int(data["presence_distance_index"])
        self.threshold_curve.setData(self.depths, data["threshold_array"])
        movement_x = data["presence_distance"]
        self.move_depth_line_slow.setPos(movement_x)
        self.move_depth_line_fast.setPos(movement_x)
        self.move_depth_line_slow.setVisible(
            bool(data["presence_detected"] and data["information"] == "slow_motion")
        )
        self.move_depth_line_fast.setVisible(
            bool(data["presence_detected"] and data["information"] == "fast_motion")
        )

        if data["information"] == "adapting_threshold":
            self.cal_implementation_item.show()
            self.cal_implementation_item.setPos(1, 0.95 * m_slow)
        else:
            self.cal_implementation_item.hide()

        move_hist_slow_ys = data["slow_history"]
        move_hist_fast_ys = data["fast_history"]
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_slow_ys))
        self.move_hist_slow_curve.setData(move_hist_xs, move_hist_slow_ys)
        self.move_hist_fast_curve.setData(move_hist_xs, move_hist_fast_ys)
        self.set_present_text_y_pos(2)
        if self.latest_fneg == data["fls_neg_s"] and self.latest_fneg > 0:
            fneg_text = "False negative is > {:.2f} s".format(self.latest_fneg)
        else:
            fneg_text = "False negative is {:.2f} s".format(self.latest_fneg)
        if self.latest_fpos == data["fls_pos_s"] and self.latest_fpos > 0:
            fpos_text = "False positive is > {:.2f} s".format(self.latest_fpos)
        else:
            fpos_text = "False positive is {:.2f} s".format(self.latest_fpos)
        self.latest_fneg = data["fls_neg_s"]
        self.latest_fpos = data["fls_pos_s"]
        self.fpos_text_item.setText(fpos_text)
        self.fneg_text_item.setText(fneg_text)
        if data["presence_detected"] and index_array_based:
            present_text = "Presence detected at {:.0f} cm".format(movement_x * 100)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)
            self.present_text_item.show()
            self.not_present_text_item.hide()

        elif data["presence_detected"]:
            present_text = "Presence detected"
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
        self.fpos_text_item.setPos(-self.history_length_s * 0.9, 0.98 * y)
        self.fneg_text_item.setPos(-self.history_length_s * 0.9, 0.8 * y)
