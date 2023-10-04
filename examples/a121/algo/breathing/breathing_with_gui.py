# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401
from PySide6.QtGui import QFont

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.a121.algo.breathing import AppState, RefApp
from acconeer.exptool.a121.algo.breathing._ref_app import (
    BreathingProcessorConfig,
    RefAppConfig,
    get_sensor_config,
)
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    # Setup the configurations
    # Detailed at https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/ref_apps/breathing.html

    # Sensor selections
    sensor = 1

    # Ref App Configurations
    breathing_processor_config = BreathingProcessorConfig(
        lowest_breathing_rate=6,
        highest_breathing_rate=60,
        time_series_length_s=20,
    )

    # Presence Configurations
    presence_config = PresenceProcessorConfig(
        intra_detection_threshold=4,
        intra_frame_time_const=0.15,
        inter_frame_fast_cutoff=20,
        inter_frame_slow_cutoff=0.2,
        inter_frame_deviation_time_const=0.5,
    )

    # Breathing Configurations
    ref_app_config = RefAppConfig(
        use_presence_processor=True,
        num_distances_to_analyze=3,
        distance_determination_duration=5,
        breathing_config=breathing_processor_config,
        presence_config=presence_config,
    )

    # End setup configurations

    # Preparation for client
    sensor_config = get_sensor_config(ref_app_config=ref_app_config)
    client = a121.Client.open(**a121.get_client_args(args))
    metadata = client.setup_session(sensor_config)

    # Preparation for reference application processor
    ref_app = RefApp(client=client, sensor_id=sensor, ref_app_config=ref_app_config)
    ref_app.start()

    pg_updater = PGUpdater(sensor_config, ref_app_config, metadata)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        processed_data = ref_app.get_next()
        try:
            pg_process.put_data(processed_data)
        except et.PGProccessDiedException:
            break

    ref_app.stop()
    print("Disconnecting...")
    client.close()


class PGUpdater:
    def __init__(
        self,
        sensor_config: a121.SensorConfig,
        ref_app_config: RefAppConfig,
        metadata: a121.Metadata,
    ):
        self.distances = get_distances_m(sensor_config, metadata)
        self.use_presence_processor = ref_app_config.use_presence_processor

    def setup(self, win):
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
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_dot, symbolPen="k")

        font = QFont()
        font.setPixelSize(16)

        # Presence plot.
        self.presence_plot = win.addPlot(row=0, col=0)
        self.presence_plot.setMenuEnabled(False)
        self.presence_plot.showGrid(x=True, y=True)
        self.presence_plot.addLegend()
        self.presence_plot.setLabel("left", "Presence score")
        self.presence_plot.setLabel("bottom", "Distance (m)")
        self.presence_plot.addItem(pg.PlotDataItem())
        self.presence_plot_curve = []
        self.presence_plot_curve.append(self.presence_plot.plot(**self.blue))
        self.presence_plot_curve.append(self.presence_plot.plot(**self.orange))
        self.presence_plot_curve.append(self.presence_plot.plot(**self.blue))
        self.presence_plot_curve.append(self.presence_plot.plot(**self.orange))

        self.presence_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        self.presence_plot_legend.setParentItem(self.presence_plot)
        self.presence_plot_legend.addItem(self.presence_plot_curve[2], "Slow motion")
        self.presence_plot_legend.addItem(self.presence_plot_curve[3], "Fast motion")
        self.presence_plot_legend.show()

        self.presence_smoot_max = et.utils.SmoothMax()

        self.presence_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.presence_text_item.setFont(font)
        self.presence_text_item.show()
        self.presence_plot.addItem(self.presence_text_item)

        # Time series plot.
        self.time_series_plot = win.addPlot(row=1, col=0)
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.addLegend()
        self.time_series_plot.setLabel("left", "Displacement")
        self.time_series_plot.setLabel("bottom", "Time (s)")
        self.time_series_plot.addItem(pg.PlotDataItem())
        self.time_series_curve = self.time_series_plot.plot(**self.blue)

        self.time_series_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.time_series_text_item.setFont(font)
        self.time_series_text_item.show()
        self.time_series_plot.addItem(self.time_series_text_item)

        # Breathing psd plot.
        self.breathing_psd_plot = win.addPlot(row=2, col=0)
        self.breathing_psd_plot.setMenuEnabled(False)
        self.breathing_psd_plot.showGrid(x=True, y=True)
        self.breathing_psd_plot.addLegend()
        self.breathing_psd_plot.setLabel("left", "PSD")
        self.breathing_psd_plot.setLabel("bottom", "Breathing rate (Hz)")
        self.breathing_psd_plot.addItem(pg.PlotDataItem())
        self.breathing_psd_curve = self.breathing_psd_plot.plot(**self.blue)

        self.psd_smoothing = et.utils.SmoothMax()

        # Breathing rate plot.
        self.breathing_rate_plot = win.addPlot(row=3, col=0)
        self.breathing_rate_plot.setMenuEnabled(False)
        self.breathing_rate_plot.showGrid(x=True, y=True)
        self.breathing_rate_plot.addLegend()
        self.breathing_rate_plot.setLabel("left", "Breaths per minute")
        self.breathing_rate_plot.setLabel("bottom", "Time (s)")
        self.breathing_rate_plot.addItem(pg.PlotDataItem())
        self.breathing_rate_curves = []
        self.breathing_rate_curves.append(self.breathing_rate_plot.plot(**self.blue))
        self.breathing_rate_curves.append(
            self.breathing_rate_plot.plot(**dict(pen=None, **symbol_dot_kw))
        )
        self.smooth_breathing_rate = et.utils.SmoothLimits()

        self.breathing_rate_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        self.breathing_rate_plot_legend.setParentItem(self.breathing_rate_plot)
        self.breathing_rate_plot_legend.addItem(self.breathing_rate_curves[0], "Breathing rate")
        self.breathing_rate_plot_legend.addItem(
            self.breathing_rate_curves[1], "Breathing rate(embedded output)"
        )
        self.breathing_rate_plot_legend.hide()

        self.breathing_rate_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.breathing_rate_text_item.setFont(font)
        self.breathing_rate_text_item.hide()
        self.breathing_rate_plot.addItem(self.breathing_rate_text_item)

    def update(self, ref_app_result):
        app_state = ref_app_result.app_state

        max_ampl = max(
            np.max(ref_app_result.presence_result.inter),
            np.max(ref_app_result.presence_result.intra),
        )
        lim = self.presence_smoot_max.update(max_ampl)
        self.presence_plot.setYRange(0, lim)

        if ref_app_result.distances_being_analyzed is None:
            self.presence_plot_curve[0].setData(
                self.distances, ref_app_result.presence_result.inter, **self.blue
            )
            self.presence_plot_curve[1].setData(
                self.distances, ref_app_result.presence_result.intra, **self.orange
            )
            self.presence_plot_curve[2].setData([], [])
            self.presence_plot_curve[3].setData([], [])
        else:
            start = ref_app_result.distances_being_analyzed[0]
            end = ref_app_result.distances_being_analyzed[1]
            s = slice(start, end)
            distance_slice = self.distances[s]
            self.presence_plot_curve[0].setData(
                self.distances,
                ref_app_result.presence_result.inter,
                pen=self.blue_transparent_pen,
            )
            self.presence_plot_curve[1].setData(
                self.distances,
                ref_app_result.presence_result.intra,
                pen=self.orange_transparent_pen,
            )
            self.presence_plot_curve[2].setData(
                distance_slice, ref_app_result.presence_result.inter[s]
            )
            self.presence_plot_curve[3].setData(
                distance_slice, ref_app_result.presence_result.intra[s]
            )

        if ref_app_result.breathing_result is not None:
            breathing_result = ref_app_result.breathing_result.extra_result
            breathing_motion = breathing_result.breathing_motion
            psd = breathing_result.psd
            frequencies = breathing_result.frequencies
            time_vector = breathing_result.time_vector
            all_breathing_rate_history = breathing_result.all_breathing_rate_history
            breathing_rate_history = breathing_result.breathing_rate_history

            self.time_series_curve.setData(
                time_vector[-breathing_motion.shape[0] :], breathing_motion
            )
            y = np.max(np.abs(breathing_motion)) * 1.05
            self.time_series_plot.setYRange(-y, y)
            self.time_series_plot.setXRange(
                time_vector[-breathing_motion.shape[0]], max(time_vector)
            )

            if not np.all(np.isnan(all_breathing_rate_history)):
                ylim = self.psd_smoothing.update(psd)
                self.breathing_psd_curve.setData(frequencies, psd)
                self.breathing_psd_plot.setYRange(0, ylim)
                self.breathing_psd_plot.setXRange(0, 2)

                self.breathing_rate_curves[0].setData(time_vector, all_breathing_rate_history)
                lims = self.smooth_breathing_rate.update(all_breathing_rate_history)
                self.breathing_rate_plot.setYRange(lims[0] - 3, lims[1] + 3)

                self.breathing_rate_plot_legend.show()

            if not np.all(np.isnan(breathing_rate_history)):
                self.breathing_rate_curves[1].setData(time_vector, breathing_rate_history)

            if not np.isnan(breathing_rate_history[-1]):
                self.displayed_breathing_rate = "{:.1f}".format(breathing_rate_history[-1])
                self.breathing_rate_text_item.show()

        else:
            self.time_series_plot.setYRange(0, 1)
            self.time_series_plot.setXRange(0, 1)
            self.time_series_curve.setData([], [])
            self.breathing_psd_curve.setData([], [])
            self.breathing_rate_curves[0].setData([], [])
            self.breathing_rate_curves[1].setData([], [])
            self.displayed_breathing_rate = None
            self.breathing_rate_text_item.hide()

        # Set text in text boxes according to app state.

        # Presence text
        if app_state == AppState.NO_PRESENCE_DETECTED:
            presence_text = "No presence detected"
        elif app_state == AppState.DETERMINE_DISTANCE_ESTIMATE:
            presence_text = "Determining distance with presence"
        elif app_state == AppState.ESTIMATE_BREATHING_RATE:
            start_m = "{:.2f}".format(distance_slice[0])
            end_m = "{:.2f}".format(distance_slice[-1])
            if self.use_presence_processor:
                presence_text = (
                    "Presence detected in the range " + start_m + " - " + end_m + " (m)"
                )
            else:
                presence_text = "Presence distance detection disabled"
        elif app_state == AppState.INTRA_PRESENCE_DETECTED:
            presence_text = "Large motion detected"
        else:
            presence_text = ""

        text_y_pos = self.presence_plot.getAxis("left").range[1] * 0.95
        text_x_pos = (
            self.presence_plot.getAxis("bottom").range[1]
            + self.presence_plot.getAxis("bottom").range[0]
        ) / 2.0
        self.presence_text_item.setPos(text_x_pos, text_y_pos)
        self.presence_text_item.setHtml(presence_text)

        # Breathing text
        if app_state == AppState.ESTIMATE_BREATHING_RATE:
            if (
                ref_app_result.breathing_result is not None
                and ref_app_result.breathing_result.breathing_rate is None
            ):
                time_series_text = "Initializing breathing detection"
            elif self.displayed_breathing_rate is not None:
                time_series_text = "Breathing rate: " + self.displayed_breathing_rate + " bpm"
        else:
            time_series_text = "Waiting for distance"

        text_y_pos = self.time_series_plot.getAxis("left").range[1] * 0.95
        text_x_pos = (
            self.time_series_plot.getAxis("bottom").range[1]
            + self.time_series_plot.getAxis("bottom").range[0]
        ) / 2.0
        self.time_series_text_item.setPos(text_x_pos, text_y_pos)
        self.time_series_text_item.setHtml(time_series_text)

        if self.displayed_breathing_rate is not None:
            text_y_pos = self.breathing_rate_plot.getAxis("left").range[1] * 0.95
            text_x_pos = time_vector[0]

            self.breathing_rate_text_item.setPos(text_x_pos, text_y_pos)
            self.breathing_rate_text_item.setHtml(self.displayed_breathing_rate + " bpm")


if __name__ == "__main__":
    main()
