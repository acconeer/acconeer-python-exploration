# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

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
        intra_frame_weight=0,
        detection_threshold=1,
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

        self.limit_lines = []
        dashed_pen = pg.mkPen("k", width=2.5, style=QtCore.Qt.DashLine)

        # Amplitude plot

        self.ampl_plot = win.addPlot(
            row=0,
            col=0,
            title="Amplitude, sweeps (orange), mean sweep (blue)",
        )

        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.setMouseEnabled(x=False, y=False)
        self.ampl_plot.hideButtons()
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Distance (m)")
        self.ampl_plot.setLabel("left", "Amplitude")

        self.ampl_plot.setYRange(0, 2**16)

        self.frame_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(1),
        )
        self.mean_sweep_scatter = pg.ScatterPlotItem(
            size=10,
            brush=et.utils.pg_brush_cycler(0),
        )

        self.ampl_plot.addItem(self.frame_scatter)
        self.ampl_plot.addItem(self.mean_sweep_scatter)
        self.frame_smooth_limits = et.utils.SmoothLimits(self.sensor_config.frame_rate)

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
        self.noise_plot.setLabel("bottom", "Distance (m)")
        self.noise_plot.setLabel("left", "Amplitude")
        self.noise_plot.setVisible(False)
        self.noise_curve = self.noise_plot.plot(pen=et.utils.pg_pen_cycler())
        self.noise_smooth_max = et.utils.SmoothMax(self.sensor_config.frame_rate)

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
        self.move_plot.setLabel("bottom", "Distance (m)")
        self.move_plot.setLabel("left", "Norm. ampl.")
        zero_curve = self.move_plot.plot(self.distances, np.zeros_like(self.distances))
        self.inter_curve = self.move_plot.plot()
        self.total_curve = self.move_plot.plot()
        self.move_smooth_max = et.utils.SmoothMax(
            self.sensor_config.frame_rate,
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
        self.history_smooth_max = et.utils.SmoothMax(self.sensor_config.frame_rate)
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

        for line in self.limit_lines:
            line.setPos(self.processor_config.detection_threshold)

        # Sector plot

        self.sector_plot = pg.PlotItem()
        self.sector_plot.setAspectLocked()
        self.sector_plot.hideAxis("left")
        self.sector_plot.hideAxis("bottom")
        self.sectors = []

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(self.num_sectors) + 1):
            sector = pg.QtGui.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
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

    def update(self, data):
        amplitudes = np.abs(data.extra_result.frame)
        self.frame_scatter.setData(
            np.tile(self.distances, self.sensor_config.sweeps_per_frame),
            amplitudes.flatten(),
        )

        self.mean_sweep_scatter.setData(self.distances, data.extra_result.mean_sweep)
        self.ampl_plot.setYRange(*self.frame_smooth_limits.update(amplitudes))

        noise = data.extra_result.lp_noise
        self.noise_curve.setData(self.distances, noise)
        self.noise_plot.setYRange(0, self.noise_smooth_max.update(noise))

        movement_x = data.presence_distance

        move_ys = data.extra_result.depthwise_presence
        self.inter_curve.setData(self.distances, data.extra_result.inter)
        self.total_curve.setData(self.distances, move_ys)
        m = self.move_smooth_max.update(np.max(move_ys))
        m = max(m, 2 * self.processor_config.detection_threshold)
        self.move_plot.setYRange(0, m)
        self.move_depth_line.setPos(movement_x)
        self.move_depth_line.setVisible(bool(data.presence_detected))

        move_hist_ys = data.extra_result.presence_history
        move_hist_xs = np.linspace(-self.history_length_s, 0, len(move_hist_ys))

        m_hist = max(np.max(move_hist_ys), self.processor_config.detection_threshold * 1.05)
        m_hist = self.history_smooth_max.update(m_hist)

        self.move_hist_plot.setYRange(0, m_hist)
        self.move_hist_curve.setData(move_hist_xs, move_hist_ys)
        self.set_present_text_y_pos(m_hist)

        if data.presence_detected:
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

        if data.presence_detected:
            index = (
                data.extra_result.presence_distance_index + self.sector_offset
            ) // self.sector_size
            self.sectors[index].setBrush(et.utils.pg_brush_cycler(1))

    def set_present_text_y_pos(self, y):
        self.present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)
        self.not_present_text_item.setPos(-self.history_length_s / 2, 0.95 * y)


if __name__ == "__main__":
    main()
