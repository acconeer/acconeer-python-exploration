# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import numpy.typing as npt

from PySide6 import QtCore

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.presence import Detector
from acconeer.exptool.a121.algo.smart_presence._ref_app import (
    PresenceWakeUpConfig,
    PresenceZoneConfig,
    RefApp,
    RefAppConfig,
    RefAppResult,
    _Mode,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    ref_app_config = RefAppConfig(
        wake_up_mode=True,
        wake_up_config=PresenceWakeUpConfig(
            start_m=1.0,
            end_m=3.0,
            num_zones=5,
            num_zones_for_wake_up=2,
        ),
        nominal_config=PresenceZoneConfig(
            start_m=1.0,
            end_m=3.0,
            num_zones=3,
        ),
    )

    ref_app = RefApp(client=client, sensor_id=1, ref_app_config=ref_app_config)
    ref_app.start()

    nominal_sensor_config = Detector._get_sensor_config(ref_app.nominal_detector_config)
    distances = np.linspace(
        ref_app_config.nominal_config.start_m,
        ref_app_config.nominal_config.end_m,
        nominal_sensor_config.num_points,
    )
    nominal_zone_limits = ref_app.ref_app_processor.create_zones(
        distances, ref_app_config.nominal_config.num_zones
    )

    pg_updater = PGUpdater(
        ref_app_config,
        ref_app.ref_app_context.wake_up_detector_context.estimated_frame_rate,
        nominal_zone_limits,
        ref_app.ref_app_processor.zone_limits,
    )
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        ref_app_result = ref_app.get_next()
        if ref_app_result.presence_detected:
            print(f"Presence in zone {ref_app_result.max_presence_zone}")
        else:
            print("No presence")
        try:
            pg_process.put_data(ref_app_result)
        except et.PGProccessDiedException:
            break

    ref_app.stop()

    print("Disconnecting...")
    client.close()


class PGUpdater:
    def __init__(
        self,
        ref_app_config: RefAppConfig,
        estimated_frame_rate: float,
        nominal_zone_limits: npt.NDArray[np.float_],
        wake_up_zone_limits: npt.NDArray[np.float_],
    ) -> None:
        self.ref_app_config = ref_app_config
        self.nominal_config = ref_app_config.nominal_config
        self.wake_up_config = ref_app_config.wake_up_config

        self.show_all_detected_zones = ref_app_config.show_all_detected_zones
        self.nominal_zone_limits = nominal_zone_limits
        self.wake_up_zone_limits = wake_up_zone_limits
        self.estimated_frame_rate = estimated_frame_rate

        self.history_length_s = 5
        self.time_fifo: List[float] = []
        self.intra_fifo: List[float] = []
        self.inter_fifo: List[float] = []

        self.intra_limit_lines = []
        self.inter_limit_lines = []

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer smart presence example")

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
        if not self.nominal_config.intra_enable:
            intra_color = et.utils.color_cycler(1)
            intra_color = f"{intra_color}50"
            self.nominal_intra_dashed_pen = pg.mkPen(
                intra_color, width=2.5, style=QtCore.Qt.DashLine
            )
            self.nominal_intra_pen = pg.mkPen(intra_color, width=2)
        else:
            self.nominal_intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            self.nominal_intra_pen = et.utils.pg_pen_cycler(1)

        self.intra_hist_curve = self.intra_hist_plot.plot(pen=self.nominal_intra_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=self.nominal_intra_dashed_pen)
        self.intra_hist_plot.addItem(limit_line)
        self.intra_limit_lines.append(limit_line)

        for line in self.intra_limit_lines:
            line.setPos(self.nominal_config.intra_detection_threshold)

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
        if not self.nominal_config.inter_enable:
            inter_color = et.utils.color_cycler(0)
            inter_color = f"{inter_color}50"
            self.nominal_inter_dashed_pen = pg.mkPen(
                inter_color, width=2.5, style=QtCore.Qt.DashLine
            )
            self.nominal_inter_pen = pg.mkPen(inter_color, width=2)
        else:
            self.nominal_inter_pen = et.utils.pg_pen_cycler(0)
            self.nominal_inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        self.inter_hist_curve = self.inter_hist_plot.plot(pen=self.nominal_inter_pen)
        limit_line = pg.InfiniteLine(angle=0, pen=self.nominal_inter_dashed_pen)
        self.inter_hist_plot.addItem(limit_line)
        self.inter_limit_lines.append(limit_line)

        for line in self.inter_limit_lines:
            line.setPos(self.nominal_config.inter_detection_threshold)

        # Sector plot

        if self.ref_app_config.wake_up_mode:
            title = (
                "Nominal config<br>"
                "Detection type: fast (orange), slow (blue), both (green)<br>"
                "Green background indicates active"
            )
        else:
            title = "Nominal config<br>" "Detection type: fast (orange), slow (blue), both (green)"

        self.nominal_sector_plot, self.nominal_sectors = self.create_sector_plot(
            title,
            self.ref_app_config.nominal_config.num_zones,
            self.nominal_config.start_m,
            self.nominal_zone_limits,
        )

        if not self.ref_app_config.wake_up_mode:
            sublayout = win.addLayout(row=1, col=0, colspan=2)
            sublayout.layout.setColumnStretchFactor(0, 2)
            sublayout.addItem(self.nominal_sector_plot, row=0, col=0)
        else:
            assert self.wake_up_config is not None
            sublayout = win.addLayout(row=1, col=0, colspan=2)
            sublayout.addItem(self.nominal_sector_plot, row=0, col=1)

            title = (
                "Wake up config<br>"
                "Detection type: fast (orange), slow (blue), both (green),<br>"
                "lingering (light grey)<br>"
                "Green background indicates active"
            )
            self.wake_up_sector_plot, self.wake_up_sectors = self.create_sector_plot(
                title,
                self.wake_up_config.num_zones,
                self.wake_up_config.start_m,
                self.wake_up_zone_limits,
            )

            sublayout.addItem(self.wake_up_sector_plot, row=0, col=0)

            if self.wake_up_config.intra_enable:
                self.wake_up_intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
                self.wake_up_intra_pen = et.utils.pg_pen_cycler(1)
            else:
                intra_color = et.utils.color_cycler(1)
                intra_color = f"{intra_color}50"
                self.wake_up_intra_dashed_pen = pg.mkPen(
                    intra_color, width=2.5, style=QtCore.Qt.DashLine
                )
                self.wake_up_intra_pen = pg.mkPen(intra_color, width=2)

            if self.wake_up_config.inter_enable:
                self.wake_up_inter_pen = et.utils.pg_pen_cycler(0)
                self.wake_up_inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")
            else:
                inter_color = et.utils.color_cycler(0)
                inter_color = f"{inter_color}50"
                self.wake_up_inter_dashed_pen = pg.mkPen(
                    inter_color, width=2.5, style=QtCore.Qt.DashLine
                )
                self.wake_up_inter_pen = pg.mkPen(inter_color, width=2)

    @staticmethod
    def create_sector_plot(
        title: str, num_sectors: int, start_m: float, zone_limits: npt.NDArray[np.float_]
    ) -> Tuple[pg.PlotItem, List[pg.QtWidgets.QGraphicsEllipseItem]]:
        sector_plot = pg.PlotItem(title=title)

        sector_plot.setAspectLocked()
        sector_plot.hideAxis("left")
        sector_plot.hideAxis("bottom")

        sectors = []
        limit_text = []

        range_html = (
            '<div style="text-align: center">'
            '<span style="color: #000000;font-size:12pt;">'
            "{}</span></div>"
        )

        if start_m == zone_limits[0]:
            x_offset = 0.7
        else:
            x_offset = 0

        pen = pg.mkPen("k", width=1)
        span_deg = 25
        for r in np.flip(np.arange(1, num_sectors + 2)):
            sector = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
            sector.setStartAngle(-16 * span_deg)
            sector.setSpanAngle(16 * span_deg * 2)
            sector.setPen(pen)
            sector_plot.addItem(sector)
            sectors.append(sector)

            if r != 1:
                limit = pg.TextItem(html=range_html, anchor=(0.5, 0.5), angle=25)
                x = r * np.cos(np.radians(span_deg))
                y = r * np.sin(np.radians(span_deg))
                limit.setPos(x - x_offset, y + 0.25)
                sector_plot.addItem(limit)
                limit_text.append(limit)

        sectors.reverse()

        if not start_m == zone_limits[0]:
            start_limit_text = pg.TextItem(html=range_html, anchor=(0.5, 0.5), angle=25)
            start_range_html = range_html.format(f"{start_m}")
            start_limit_text.setHtml(start_range_html)
            x = 1 * np.cos(np.radians(span_deg))
            y = 1 * np.sin(np.radians(span_deg))

            start_limit_text.setPos(x, y + 0.25)
            sector_plot.addItem(start_limit_text)

        unit_text = pg.TextItem(html=range_html, anchor=(0.5, 0.5))
        unit_html = range_html.format("[m]")
        unit_text.setHtml(unit_html)
        x = (num_sectors + 2) * np.cos(np.radians(span_deg))
        y = (num_sectors + 2) * np.sin(np.radians(span_deg))
        unit_text.setPos(x - x_offset, y + 0.25)
        sector_plot.addItem(unit_text)

        for text_item, limit in zip(limit_text, np.flip(zone_limits)):
            zone_range_html = range_html.format(np.around(limit, 1))
            text_item.setHtml(zone_range_html)

        return sector_plot, sectors

    def update(self, data: RefAppResult) -> None:
        if data.used_config == _Mode.NOMINAL_CONFIG:
            inter_threshold = self.nominal_config.inter_detection_threshold
            intra_threshold = self.nominal_config.intra_detection_threshold
            intra_pen = self.nominal_intra_pen
            intra_dashed_pen = self.nominal_intra_dashed_pen
            inter_pen = self.nominal_inter_pen
            inter_dashed_pen = self.nominal_inter_dashed_pen
        else:
            assert self.wake_up_config is not None
            inter_threshold = self.wake_up_config.inter_detection_threshold
            intra_threshold = self.wake_up_config.intra_detection_threshold
            intra_pen = self.wake_up_intra_pen
            intra_dashed_pen = self.wake_up_intra_dashed_pen
            inter_pen = self.wake_up_inter_pen
            inter_dashed_pen = self.wake_up_inter_dashed_pen

        self.time_fifo.append(data.service_result.tick_time)

        if data.switch_delay:
            self.intra_fifo.append(float("nan"))
            self.inter_fifo.append(float("nan"))
        else:
            self.intra_fifo.append(data.intra_presence_score)
            self.inter_fifo.append(data.inter_presence_score)

        while self.time_fifo[-1] - self.time_fifo[0] > self.history_length_s:
            self.time_fifo.pop(0)
            self.intra_fifo.pop(0)
            self.inter_fifo.pop(0)

        times = [t - self.time_fifo[-1] for t in self.time_fifo]

        # Intra presence

        if np.isnan(self.intra_fifo).all():
            m_hist = intra_threshold
        else:
            m_hist = np.maximum(float(np.nanmax(self.intra_fifo)), intra_threshold * 1.05)

        m_hist = self.intra_history_smooth_max.update(m_hist)

        self.intra_hist_plot.setYRange(0, m_hist)
        self.intra_hist_curve.setData(times, self.intra_fifo, connect="finite")
        self.intra_hist_curve.setPen(intra_pen)

        for line in self.intra_limit_lines:
            line.setPos(intra_threshold)
            line.setPen(intra_dashed_pen)

        # Inter presence

        if np.isnan(self.inter_fifo).all():
            m_hist = inter_threshold
        else:
            m_hist = np.maximum(float(np.nanmax(self.inter_fifo)), inter_threshold * 1.05)

        m_hist = self.inter_history_smooth_max.update(m_hist)

        self.inter_hist_plot.setYRange(0, m_hist)
        self.inter_hist_curve.setData(times, self.inter_fifo, connect="finite")
        self.inter_hist_curve.setPen(inter_pen)

        for line in self.inter_limit_lines:
            line.setPos(inter_threshold)
            line.setPen(inter_dashed_pen)

        # Sector

        brush = et.utils.pg_brush_cycler(7)
        for sector in self.nominal_sectors:
            sector.setBrush(brush)

        if not self.ref_app_config.wake_up_mode:
            sectors = self.nominal_sectors[1:]
            show_all_zones = self.show_all_detected_zones
            color_nominal = "white"
        else:
            if data.used_config == _Mode.WAKE_UP_CONFIG:
                sectors = self.wake_up_sectors[1:]
                show_all_zones = True
                color_wake_up = "#DFF1D6"
                color_nominal = "white"
            else:
                sectors = self.nominal_sectors[1:]
                show_all_zones = self.show_all_detected_zones
                color_wake_up = "white"
                color_nominal = "#DFF1D6"

            vb = self.nominal_sector_plot.getViewBox()
            vb.setBackgroundColor(color_nominal)
            vb = self.wake_up_sector_plot.getViewBox()
            vb.setBackgroundColor(color_wake_up)

            for sector in self.wake_up_sectors:
                sector.setBrush(brush)

        if data.presence_detected:
            self.color_zones(data, show_all_zones, sectors)
            self.switch_data = data
        elif data.switch_delay:
            self.color_zones(self.switch_data, True, self.wake_up_sectors[1:])

        self.nominal_sectors[0].setPen(pg.mkPen(color_nominal, width=1))
        self.nominal_sectors[0].setBrush(pg.mkBrush(color_nominal))

        if self.ref_app_config.wake_up_mode:
            self.wake_up_sectors[0].setPen(pg.mkPen(color_wake_up, width=1))
            self.wake_up_sectors[0].setBrush(pg.mkBrush(color_wake_up))

    @staticmethod
    def color_zones(
        data: RefAppResult,
        show_all_detected_zones: bool,
        sectors: List[pg.QtWidgets.QGraphicsEllipseItem],
    ) -> None:
        if show_all_detected_zones:
            for zone, (inter_value, intra_value) in enumerate(
                zip(data.inter_zone_detections, data.intra_zone_detections)
            ):
                if inter_value + intra_value == 2:
                    sectors[zone].setBrush(et.utils.pg_brush_cycler(2))
                elif inter_value == 1:
                    sectors[zone].setBrush(et.utils.pg_brush_cycler(0))
                elif intra_value == 1:
                    sectors[zone].setBrush(et.utils.pg_brush_cycler(1))
                elif data.used_config == _Mode.WAKE_UP_CONFIG:
                    assert data.wake_up_detections is not None
                    if data.wake_up_detections[zone] > 0:
                        sectors[zone].setBrush(pg.mkBrush("#b5afa0"))
        else:
            assert data.max_presence_zone is not None
            if data.max_presence_zone == data.max_intra_zone:
                sectors[data.max_presence_zone].setBrush(et.utils.pg_brush_cycler(1))
            else:
                sectors[data.max_presence_zone].setBrush(et.utils.pg_brush_cycler(0))


if __name__ == "__main__":
    main()
