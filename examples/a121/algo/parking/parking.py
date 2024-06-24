# Copyright (c) Acconeer AB, 2023-2024
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
from acconeer.exptool.a121.algo.parking import (
    ObstructionProcessor,
    RefApp,
    RefAppConfig,
    RefAppResult,
)
from acconeer.exptool.a121.algo.parking._processors import MAX_AMPLITUDE
from acconeer.exptool.a121.algo.parking._ref_app import get_sensor_configs


SENSOR_ID = 1


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))
    ref_app_config = RefAppConfig(
        range_start_m=0.1,
        range_end_m=0.4,
        hwaas=24,
        profile=a121.Profile.PROFILE_1,
        update_rate=5,
        queue_length_n=3,
        amplitude_threshold=8.0,
        weighted_distance_threshold_m=0.1,
        obstruction_detection=True,
        obstruction_start_m=0.03,
        obstruction_end_m=0.05,
        obstruction_distance_threshold=0.06,
    )

    ref_app = RefApp(client=client, sensor_id=SENSOR_ID, ref_app_config=ref_app_config)
    ref_app.calibrate_ref_app()
    ref_app.start()

    pg_updater = PGUpdater(
        ref_app_config,
        ref_app.metadata,
        SENSOR_ID,
        ref_app.session_config,
    )

    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        ref_app_result = ref_app.get_next()
        if ref_app_result.car_detected:
            print("Car detected")
        else:
            print("No car detected")
        if ref_app_config.obstruction_detection:
            if ref_app_result.obstruction_detected:
                print("Obstruction detected")
            else:
                print("No obstruction detected")
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
        metadata: a121.Metadata,
        sensor_id: int,
        session_config: a121.SessionConfig,
    ):
        self.metadata = metadata
        self.ref_app_config = ref_app_config
        sensor_configs = get_sensor_configs(ref_app_config)
        display_config = sensor_configs["base_config"]
        self.sensor_id = sensor_id
        self.session_config = session_config
        self.sensor_config = display_config
        self.distances = get_distances_m(display_config, metadata)

        if self.ref_app_config.obstruction_detection:
            obstruction_config = sensor_configs["obstruction_config"]
            self.obs_distances = get_distances_m(obstruction_config, metadata)
            self.obs_x_thres, self.obs_y_thres = ObstructionProcessor.get_thresholds(
                ref_app_config.obstruction_distance_threshold, self.obs_distances
            )

        self.setup_is_done = False

    def setup(self, win):
        win.setWindowTitle("Acconeer parking detection example")
        # Define pens and font.
        blue_color = et.utils.color_cycler(0)
        orange_color = et.utils.color_cycler(1)
        brush = et.utils.pg_brush_cycler(0)

        self.blue = dict(
            pen=pg.mkPen(blue_color, width=2),
            symbol="o",
            symbolSize=1,
            symbolBrush=brush,
            symbolPen="k",
        )

        self.orange = dict(
            pen=pg.mkPen(orange_color, width=2),
            symbol="o",
            symbolSize=1,
            symbolBrush=brush,
            symbolPen="k",
        )
        self.blue_transparent_pen = pg.mkPen(f"{blue_color}50", width=2)
        self.orange_transparent_pen = pg.mkPen(f"{orange_color}50", width=2)

        brush_dot = et.utils.pg_brush_cycler(1)

        # Signature plot.
        self.sig_plot = win.addPlot(row=0, col=0, colspan=2)
        self.sig_plot.setTitle("Sampled Signatures")
        self.sig_plot.setMenuEnabled(False)
        self.sig_plot.showGrid(x=True, y=True)
        self.sig_plot.addLegend()
        self.sig_plot.setLabel("left", "Normalized energy")
        self.sig_plot.setLabel("bottom", "Distance (m)")
        self.sig_plot.addItem(pg.PlotDataItem())
        self.sig_plot_x_range = (
            min(self.distances),
            max(self.distances) + self.ref_app_config.weighted_distance_threshold_m,
        )

        self.sig_plot.setXRange(self.sig_plot_x_range[0], self.sig_plot_x_range[1])
        self.sig_plot.setYRange(0, 100)
        symbol_kw_main = dict(
            symbol="o", symbolSize=7, symbolBrush=brush, symbolPen=None, pen=None
        )
        self.sig_plot_curve = self.sig_plot.plot(**symbol_kw_main)
        energy_threshold_line = pg.InfiniteLine(
            angle=0, pen=pg.mkPen("k", width=1.5, style=QtCore.Qt.PenStyle.DashLine)
        )
        energy_threshold_line.setVisible(True)
        energy_threshold_line.setPos(self.ref_app_config.amplitude_threshold)
        self.sig_plot.addItem(energy_threshold_line)

        self.sig_plot_cluster_start = pg.InfiniteLine(angle=90, pen=pg.mkPen("k", width=1.5))
        self.sig_plot_cluster_start.setVisible(True)
        self.sig_plot.addItem(self.sig_plot_cluster_start)

        self.sig_plot_cluster_end = pg.InfiniteLine(angle=90, pen=pg.mkPen("k", width=1.5))
        self.sig_plot_cluster_end.setVisible(True)
        self.sig_plot.addItem(self.sig_plot_cluster_end)

        self.sig_plot_smooth_max = et.utils.SmoothMax(self.session_config.update_rate)

        parking_car_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Parked car detected!")
        )
        self.parking_car_text_item = pg.TextItem(
            html=parking_car_html,
            fill=orange_color,
            anchor=(0.5, 0),
        )
        parking_no_car_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("No car detected.")
        )
        self.parking_no_car_text_item = pg.TextItem(
            html=parking_no_car_html,
            fill=blue_color,
            anchor=(0.5, 0),
        )

        self.sig_plot.addItem(self.parking_car_text_item)
        self.sig_plot.addItem(self.parking_no_car_text_item)
        self.parking_car_text_item.hide()
        self.parking_no_car_text_item.hide()

        self.cluster_width = self.ref_app_config.weighted_distance_threshold_m

        # Obstruction plot.
        if self.ref_app_config.obstruction_detection:
            self.obstruction_plot = win.addPlot(row=1, col=1)
            self.obstruction_plot.setTitle("Obstruction Detection Signatures")
            self.obstruction_plot.setMenuEnabled(False)
            self.obstruction_plot.showGrid(x=True, y=True)
            self.obstruction_plot.addLegend()
            self.obstruction_plot.setLabel("left", "Average energy")
            self.obstruction_plot.setLabel("bottom", "Distance (m)")
            self.obstruction_plot.addItem(pg.PlotDataItem())
            self.obstruction_plot.setXRange(min(self.obs_distances), max(self.obs_distances))
            self.obstruction_plot.setYRange(0, MAX_AMPLITUDE)  # Set to standard
            self.obstruction_plot_curve = self.obstruction_plot.plot(**self.orange)

            symbol_obstruction_dot = dict(
                symbol="o",
                symbolSize=7,
                symbolBrush=brush_dot,
                symbolPen=None,
                pen=None,
            )
            self.obstruction_plot_point = self.obstruction_plot.plot(**symbol_obstruction_dot)

            symbol_kw_main = dict(
                symbol="o", symbolSize=7, symbolBrush=brush, symbolPen=None, pen=None
            )
            self.obstruction_plot_center = self.obstruction_plot.plot(**symbol_kw_main)

            self.obstruction_center_rect = pg.QtWidgets.QGraphicsRectItem(0, 0, 0.01, 0.01)
            self.obstruction_center_rect.setPen(self.orange_transparent_pen)
            self.obstruction_plot.addItem(self.obstruction_center_rect)

            obstruction_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:15pt;">'
                "{}</span></div>".format("Obstruction detected!")
            )
            self.obstruction_text_item = pg.TextItem(
                html=obstruction_html,
                fill=orange_color,
                anchor=(0.5, 0),
            )
            no_obstruction_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:15pt;">'
                "{}</span></div>".format("No obstruction detected.")
            )
            self.no_obstruction_text_item = pg.TextItem(
                html=no_obstruction_html,
                fill=blue_color,
                anchor=(0.5, 0),
            )

            obs_text_x_pos = (
                min(self.obs_distances) + (max(self.obs_distances) - min(self.obs_distances)) * 0.5
            )
            obs_text_y_pos = MAX_AMPLITUDE * 0.9

            self.obstruction_text_item.setPos(obs_text_x_pos, obs_text_y_pos)
            self.no_obstruction_text_item.setPos(obs_text_x_pos, obs_text_y_pos)

            self.obstruction_plot.addItem(self.obstruction_text_item)
            self.obstruction_plot.addItem(self.no_obstruction_text_item)
            self.obstruction_text_item.hide()
            self.no_obstruction_text_item.hide()

        # Parking info plot.
        self.parking_plot = win.addPlot(row=1, col=0)
        self.parking_plot.setTitle("Noise adjusted amplitude")
        self.parking_plot.setMenuEnabled(False)
        self.parking_plot.showGrid(x=True, y=True)
        self.parking_plot.setLabel("left", "Normalized energy")
        self.parking_plot.setLabel("bottom", "Distance (m)")
        self.parking_plot.addItem(pg.PlotDataItem())
        self.parking_plot.setXRange(min(self.distances), max(self.distances))
        self.parking_plot.setYRange(0, 100)  # Set to standard
        self.parking_plot_curve = self.parking_plot.plot(**self.blue)
        self.parking_smooth_max = et.utils.SmoothMax(self.session_config.update_rate)

    def update_obstruction_text(self) -> None:
        self.obstruction_text_timeout -= 1
        if self.obstruction_text_timeout < 0:
            self.obstruction_text_timeout = 0
            self.obstruction_text_item.hide()

    def show_obstruction_text(self) -> None:
        self.obstruction_text_timeout = 5
        self.obstruction_text_item.show()

    def update(self, ref_app_result: RefAppResult) -> None:
        signatures = ref_app_result.extra_result.signature_history
        parking_data = ref_app_result.extra_result.parking_data

        signature_x = [elm[0] for elm in signatures]
        signature_y = [elm[1] for elm in signatures]

        cluster_start = ref_app_result.extra_result.closest_object_dist
        cluster_end = cluster_start + self.cluster_width
        self.sig_plot_curve.setData(x=signature_x, y=signature_y)
        self.sig_plot_cluster_start.setPos(cluster_start)
        self.sig_plot_cluster_end.setPos(cluster_end)
        self.sig_plot_cluster_start.setVisible(False)
        self.sig_plot_cluster_end.setVisible(False)

        sig_max = self.sig_plot_smooth_max.update(max(signature_y))
        self.sig_plot.setYRange(0, sig_max)

        sig_text_x_pos = (
            self.sig_plot_x_range[0] + (self.sig_plot_x_range[1] - self.sig_plot_x_range[0]) * 0.5
        )
        sig_text_y_pos = sig_max * 0.9

        self.parking_car_text_item.setPos(sig_text_x_pos, sig_text_y_pos)
        self.parking_no_car_text_item.setPos(sig_text_x_pos, sig_text_y_pos)

        if ref_app_result.car_detected:
            self.parking_no_car_text_item.hide()
            self.parking_car_text_item.show()
            self.sig_plot_cluster_start.setVisible(True)
            self.sig_plot_cluster_end.setVisible(True)
        else:
            self.parking_car_text_item.hide()
            self.parking_no_car_text_item.show()

        if self.ref_app_config.obstruction_detection:
            obstruction_data = ref_app_result.extra_result.obstruction_data
            self.obstruction_plot_curve.setData(self.obs_distances, obstruction_data)
            point_x, point_y = ref_app_result.extra_result.obstruction_signature
            center_x, center_y = ref_app_result.extra_result.obstruction_center
            rect_x = center_x - self.obs_x_thres
            rect_y = center_y - self.obs_y_thres
            rect_w = 2 * self.obs_x_thres
            rect_h = 2 * self.obs_y_thres

            self.obstruction_center_rect.setRect(rect_x, rect_y, rect_w, rect_h)

            self.obstruction_plot_point.setData(x=[point_x], y=[point_y])
            self.obstruction_plot_center.setData(x=[center_x], y=[center_y])

            if ref_app_result.obstruction_detected:
                self.no_obstruction_text_item.hide()
                self.obstruction_text_item.show()
            else:
                self.obstruction_text_item.hide()
                self.no_obstruction_text_item.show()

        park_max = np.amax(parking_data)
        park_max = self.parking_smooth_max.update(park_max)
        self.parking_plot.setYRange(0, park_max)
        self.parking_plot_curve.setData(self.distances, parking_data)


if __name__ == "__main__":
    main()
