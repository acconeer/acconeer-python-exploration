# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401
from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.a121.algo.presence import Processor, ProcessorConfig


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    sensor_config = a121.SensorConfig(
        start_point=600,
        step_length=120,
        num_points=5,
        profile=a121.Profile.PROFILE_5,
        sweeps_per_frame=32,
        hwaas=32,
        frame_rate=20,
    )

    metadata = client.setup_session(sensor_config)

    presence_config = ProcessorConfig(
        intra_detection_threshold=1.3,
        inter_detection_threshold=1,
    )

    presence_processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=presence_config,
    )

    pg_updater = PGUpdater(sensor_config, presence_config, metadata)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        processed_data = presence_processor.process(result)
        try:
            pg_process.put_data(processed_data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self, sensor_config, processor_config, metadata):
        self.sensor_config = sensor_config
        self.processor_config = processor_config

        self.history_length_s = processor_config.history_length_s
        self.distances, _ = get_distances_m(self.sensor_config, metadata)

        max_num_of_sectors = max(6, self.distances.size // 3)
        self.sector_size = max(1, -(-self.distances.size // max_num_of_sectors))
        self.num_sectors = -(-self.distances.size // self.sector_size)
        self.sector_offset = (self.num_sectors * self.sector_size - self.distances.size) // 2

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer presence detection example")

        self.intra_limit_lines = []
        self.inter_limit_lines = []

        # Noise estimation plot

        self.noise_plot = win.addPlot(
            row=0,
            col=0,
            title="Noise",
        )
        self.noise_plot.setMenuEnabled(False)
        self.noise_plot.setMouseEnabled(x=False, y=False)
        self.noise_plot.hideButtons()
        self.noise_plot.showGrid(x=True, y=True)
        self.noise_plot.setLabel("bottom", "Distance (m)")
        self.noise_plot.setLabel("left", "Amplitude")
        self.noise_plot.setVisible(False)
        self.noise_curve = self.noise_plot.plot(pen=et.utils.pg_pen_cycler())
        self.noise_smooth_max = et.utils.SmoothMax(self.sensor_config.frame_rate)

        # Depthwise presence plot

        self.move_plot = pg.PlotItem(title="Depthwise presence")
        self.move_plot.setMenuEnabled(False)
        self.move_plot.setMouseEnabled(x=False, y=False)
        self.move_plot.hideButtons()
        self.move_plot.showGrid(x=True, y=True)
        self.move_plot.setLabel("bottom", "Distance (m)")
        self.move_plot.setLabel("left", "Norm. ampl.")
        self.move_plot.setXRange(self.distances[0], self.distances[-1])
        self.intra_curve = self.move_plot.plot(pen=et.utils.pg_pen_cycler(1))
        if not self.processor_config.intra_enable:
            self.intra_curve.hide()

        self.inter_curve = self.move_plot.plot(pen=et.utils.pg_pen_cycler(0))
        if not self.processor_config.inter_enable:
            self.inter_curve.hide()

        self.move_smooth_max = et.utils.SmoothMax(
            self.sensor_config.frame_rate,
            tau_decay=1.0,
            tau_grow=0.25,
        )

        self.move_depth_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5))
        self.move_depth_line.hide()
        self.move_plot.addItem(self.move_depth_line)

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

        self.move_plot.addItem(self.present_text_item)
        self.move_plot.addItem(self.not_present_text_item)
        self.present_text_item.hide()
        self.not_present_text_item.hide()

        # Intra presence history plot

        self.intra_hist_plot = win.addPlot(
            row=1,
            col=0,
            title="Intra presence history (fast motions)",
        )
        self.intra_hist_plot.setMenuEnabled(False)
        self.intra_hist_plot.setMouseEnabled(x=False, y=False)
        self.intra_hist_plot.hideButtons()
        self.intra_hist_plot.showGrid(x=True, y=True)
        self.intra_hist_plot.setLabel("bottom", "Time (s)")
        self.intra_hist_plot.setLabel("left", "Score")
        self.intra_hist_plot.setXRange(-self.history_length_s, 0)
        self.intra_history_smooth_max = et.utils.SmoothMax(self.sensor_config.frame_rate)
        self.intra_hist_plot.setYRange(0, 10)
        if not self.processor_config.intra_enable:
            intra_color = et.utils.color_cycler(1)
            intra_color = f"{intra_color}50"
            intra_dashed_pen = pg.mkPen(intra_color, width=2.5, style=QtCore.Qt.DashLine)
            intra_pen = pg.mkPen(intra_color, width=2)
        else:
            intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            intra_pen = et.utils.pg_pen_cycler(1)

        self.intra_hist_curve = self.intra_hist_plot.plot(pen=intra_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=intra_dashed_pen)
        self.intra_hist_plot.addItem(limit_line)
        self.intra_limit_lines.append(limit_line)

        for line in self.intra_limit_lines:
            line.setPos(self.processor_config.intra_detection_threshold)

        # Inter presence history plot

        self.inter_hist_plot = win.addPlot(
            row=1,
            col=1,
            title="Inter presence history (slow motions)",
        )
        self.inter_hist_plot.setMenuEnabled(False)
        self.inter_hist_plot.setMouseEnabled(x=False, y=False)
        self.inter_hist_plot.hideButtons()
        self.inter_hist_plot.showGrid(x=True, y=True)
        self.inter_hist_plot.setLabel("bottom", "Time (s)")
        self.inter_hist_plot.setLabel("left", "Score")
        self.inter_hist_plot.setXRange(-self.history_length_s, 0)
        self.inter_history_smooth_max = et.utils.SmoothMax(self.sensor_config.frame_rate)
        self.inter_hist_plot.setYRange(0, 10)
        if not self.processor_config.inter_enable:
            inter_color = et.utils.color_cycler(0)
            inter_color = f"{inter_color}50"
            inter_dashed_pen = pg.mkPen(inter_color, width=2.5, style=QtCore.Qt.DashLine)
            inter_pen = pg.mkPen(inter_color, width=2)
        else:
            inter_pen = et.utils.pg_pen_cycler(0)
            inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        self.inter_hist_curve = self.inter_hist_plot.plot(pen=inter_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=inter_dashed_pen)
        self.inter_hist_plot.addItem(limit_line)
        self.inter_limit_lines.append(limit_line)

        for line in self.inter_limit_lines:
            line.setPos(self.processor_config.inter_detection_threshold)

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

        sublayout = win.addLayout(row=2, col=0, colspan=2)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.move_plot, row=0, col=0)
        sublayout.addItem(self.sector_plot, row=0, col=1)

        self.setup_is_done = True

    def update(self, data):
        noise = data.extra_result.lp_noise
        self.noise_curve.setData(self.distances, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(noise))

        movement_x = data.presence_distance

        self.inter_curve.setData(self.distances, data.extra_result.inter)
        self.intra_curve.setData(self.distances, data.extra_result.intra)
        m = self.move_smooth_max.update(
            np.max(np.maximum(data.extra_result.inter, data.extra_result.intra))
        )
        m = max(
            m,
            2
            * np.maximum(
                self.processor_config.intra_detection_threshold,
                self.processor_config.inter_detection_threshold,
            ),
        )
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(bool(data.presence_detected))

        self.set_present_text_y_pos(m)

        if data.presence_detected:
            present_text = "Presence detected at {:.0f} cm".format(movement_x * 100)
            present_html = self.present_html_format.format(present_text)
            self.present_text_item.setHtml(present_html)

            self.present_text_item.show()
            self.not_present_text_item.hide()
        else:
            self.present_text_item.hide()
            self.not_present_text_item.show()

        # Intra presence

        move_hist_ys = data.extra_result.intra_presence_history
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_ys))

        m_hist = max(
            float(np.max(move_hist_ys)), self.processor_config.intra_detection_threshold * 1.05
        )
        m_hist = self.intra_history_smooth_max.update(m_hist)

        self.intra_hist_plot.setYRange(0, m_hist)
        self.intra_hist_curve.setData(move_hist_xs, move_hist_ys)

        # Inter presence

        move_hist_ys = data.extra_result.inter_presence_history
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_ys))

        m_hist = max(
            float(np.max(move_hist_ys)), self.processor_config.inter_detection_threshold * 1.05
        )
        m_hist = self.inter_history_smooth_max.update(m_hist)

        self.inter_hist_plot.setYRange(0, m_hist)
        self.inter_hist_curve.setData(move_hist_xs, move_hist_ys)

        # Sector

        brush = et.utils.pg_brush_cycler(0)
        for sector in self.sectors:
            sector.setBrush(brush)

        if data.presence_detected:
            index = (
                data.extra_result.presence_distance_index + self.sector_offset
            ) // self.sector_size
            self.sectors[index].setBrush(et.utils.pg_brush_cycler(1))

    def set_present_text_y_pos(self, y):
        x_pos = self.distances[0] + (self.distances[-1] - self.distances[0]) / 2
        self.present_text_item.setPos(x_pos, 0.95 * y)
        self.not_present_text_item.setPos(x_pos, 0.95 * y)


if __name__ == "__main__":
    main()
