# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo import presence, smart_presence


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    processor_config = smart_presence.ProcessorConfig(
        num_zones=3,
    )

    detector_config = presence.DetectorConfig(
        start_m=1,
        end_m=3,
    )

    presence_detector = presence.Detector(
        client=client, sensor_id=1, detector_config=detector_config
    )
    presence_detector.start()

    smart_presence_processor = smart_presence.Processor(
        processor_config,
        detector_config,
        presence_detector.session_config,
        presence_detector.detector_metadata,
    )

    pg_updater = PGUpdater(
        detector_config,
        processor_config,
        presence_detector._get_sensor_config(detector_config),
        presence_detector.estimated_frame_rate,
        smart_presence_processor.zone_limits,
    )
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        detector_result = presence_detector.get_next()
        processor_result = smart_presence_processor.process(detector_result)
        if detector_result.presence_detected:
            print(f"Presence in zone {processor_result.max_presence_zone}")
        else:
            print("No presence")

        data = {
            "processor_result": processor_result,
            "detector_result": detector_result,
        }
        try:
            pg_process.put_data(data)
        except et.PGProccessDiedException:
            break

    presence_detector.stop()

    print("Disconnecting...")
    client.close()


class PGUpdater:
    def __init__(
        self,
        detector_config: presence.DetectorConfig,
        processor_config: smart_presence.ProcessorConfig,
        sensor_config: a121.SensorConfig,
        estimated_frame_rate: float,
        zone_limits: npt.NDArray[np.float_],
    ):
        self.detector_config = detector_config

        self.history_length_s = 5
        self.estimated_frame_rate = estimated_frame_rate
        self.history_length_n = int(round(self.history_length_s * estimated_frame_rate))
        self.intra_history = np.zeros(self.history_length_n)
        self.inter_history = np.zeros(self.history_length_n)

        self.num_sectors = min(processor_config.num_zones, sensor_config.num_points)
        self.sector_size = max(1, -(-sensor_config.num_points // self.num_sectors))

        self.sector_offset = (self.num_sectors * self.sector_size - sensor_config.num_points) // 2
        self.zone_limits = zone_limits

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer smart presence example")

        self.intra_limit_lines = []
        self.inter_limit_lines = []

        # Intra presence history plot

        self.intra_hist_plot = win.addPlot(
            row=0,
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
        self.intra_history_smooth_max = et.utils.SmoothMax(self.estimated_frame_rate)
        self.intra_hist_plot.setYRange(0, 10)
        if not self.detector_config.intra_enable:
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
            line.setPos(self.detector_config.intra_detection_threshold)

        # Inter presence history plot

        self.inter_hist_plot = win.addPlot(
            row=0,
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
        self.inter_history_smooth_max = et.utils.SmoothMax(self.estimated_frame_rate)
        self.inter_hist_plot.setYRange(0, 10)
        if not self.detector_config.inter_enable:
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
            line.setPos(self.detector_config.inter_detection_threshold)

        # Sector plot

        self.sector_plot = pg.PlotItem(
            title="Detection zone<br>Detection type: fast (orange), slow (blue), both (green)"
        )
        self.sector_plot.setAspectLocked()
        self.sector_plot.hideAxis("left")
        self.sector_plot.hideAxis("bottom")
        self.sectors = []
        self.limit_text = []

        self.range_html = (
            '<div style="text-align: center">'
            '<span style="color: #000000;font-size:12pt;">'
            "{}</span></div>"
        )

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(self.num_sectors) + 1):
            sector = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            self.sector_plot.addItem(sector)
            self.sectors.append(sector)

            limit = pg.TextItem(html=self.range_html, anchor=(0.5, 0.5), angle=25)
            x = r * np.cos(np.radians(span_deg))
            y = r * np.sin(np.radians(span_deg))
            limit.setPos(x, y + 0.25)
            self.sector_plot.addItem(limit)
            self.limit_text.append(limit)

        self.sectors.reverse()

        start_limit_text = pg.TextItem(html=self.range_html, anchor=(0.5, 0.5), angle=25)
        range_html = self.range_html.format(f"{self.detector_config.start_m}")
        start_limit_text.setHtml(range_html)
        start_limit_text.setPos(0, 0.25)
        self.sector_plot.addItem(start_limit_text)

        unit_text = pg.TextItem(html=self.range_html, anchor=(0.5, 0.5))
        unit_html = self.range_html.format("[m]")
        unit_text.setHtml(unit_html)
        unit_text.setPos(
            self.num_sectors + 0.5, (self.num_sectors + 1) * np.sin(np.radians(span_deg))
        )
        self.sector_plot.addItem(unit_text)

        for (text_item, limit) in zip(self.limit_text, np.flip(self.zone_limits)):
            range_html = self.range_html.format(np.around(limit, 1))
            text_item.setHtml(range_html)

        sublayout = win.addLayout(row=1, col=0, colspan=2)
        sublayout.layout.setColumnStretchFactor(0, 2)
        sublayout.addItem(self.sector_plot, row=0, col=0)

        self.setup_is_done = True

    def update(self, data):
        processor_result = data["processor_result"]
        detector_result = data["detector_result"]

        # Intra presence

        move_hist_xs = np.linspace(-self.history_length_s, 0, self.history_length_n)

        self.intra_history = np.roll(self.intra_history, -1)
        self.intra_history[-1] = detector_result.intra_presence_score

        m_hist = max(
            float(np.max(self.intra_history)),
            self.detector_config.intra_detection_threshold * 1.05,
        )
        m_hist = self.intra_history_smooth_max.update(m_hist)

        self.intra_hist_plot.setYRange(0, m_hist)
        self.intra_hist_curve.setData(move_hist_xs, self.intra_history)

        # Inter presence

        self.inter_history = np.roll(self.inter_history, -1)
        self.inter_history[-1] = detector_result.inter_presence_score

        m_hist = max(
            float(np.max(self.inter_history)),
            self.detector_config.inter_detection_threshold * 1.05,
        )
        m_hist = self.inter_history_smooth_max.update(m_hist)

        self.inter_hist_plot.setYRange(0, m_hist)
        self.inter_hist_curve.setData(move_hist_xs, self.inter_history)

        # Sector

        brush = et.utils.pg_brush_cycler(7)
        for sector in self.sectors:
            sector.setBrush(brush)

        if detector_result.presence_detected:
            assert processor_result.max_presence_zone is not None
            if processor_result.max_presence_zone == processor_result.max_intra_zone:
                self.sectors[processor_result.max_presence_zone].setBrush(
                    et.utils.pg_brush_cycler(1)
                )
            else:
                self.sectors[processor_result.max_presence_zone].setBrush(
                    et.utils.pg_brush_cycler(0)
                )


if __name__ == "__main__":
    main()
