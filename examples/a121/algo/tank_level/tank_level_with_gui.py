# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging

import attrs
import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import (
    PeakSortingMethod,
    ReflectorShape,
    ThresholdMethod,
)
from acconeer.exptool.a121.algo.distance._processors import (
    DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE,
    DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE,
)
from acconeer.exptool.a121.algo.tank_level import RefApp, RefAppResult
from acconeer.exptool.a121.algo.tank_level._processor import ProcessorLevelStatus
from acconeer.exptool.a121.algo.tank_level._ref_app import RefAppConfig, RefAppContext


log = logging.getLogger(__name__)


TIME_HISTORY_S = 30


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: RefAppConfig = attrs.field(factory=RefAppConfig)
    context: RefAppContext = attrs.field(factory=RefAppContext)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    # Setup the configurations
    # Detailed at https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/ref_apps/tank_level.html

    # Sensor selections
    sensor = 1

    # Tank level configurations
    ref_app_config = RefAppConfig(
        start_m=0.03,
        end_m=0.5,
        max_step_length=2,
        max_profile=a121.Profile.PROFILE_2,
        close_range_leakage_cancellation=True,
        signal_quality=20,
        update_rate=None,
        median_filter_length=5,
        num_medians_to_average=5,
        threshold_method=ThresholdMethod.CFAR,
        reflector_shape=ReflectorShape.PLANAR,
        peaksorting_method=PeakSortingMethod.CLOSEST,
        num_frames_in_recorded_threshold=50,
        fixed_threshold_value=DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE,  # float
        fixed_strength_threshold_value=DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE,  # float
        threshold_sensitivity=0.0,  # float
        level_tracking_active=False,
        partial_tracking_range_m=0.0,
    )

    # End setup configurations

    # Preparation for client
    client = a121.Client.open(**a121.get_client_args(args))

    # Preparation for reference application processor
    ref_app = RefApp(client=client, sensor_id=sensor, config=ref_app_config)
    ref_app.calibrate()
    ref_app.start()

    pg_updater = PGUpdater(
        config=ref_app_config, num_curves=len(ref_app._detector.processor_specs)
    )
    pg_process = et.PGProcess(pg_updater, max_freq=60)
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
    client.close()
    print("Disconnecting...")


class PGUpdater:
    STATUS_MSG_MAP = {
        ProcessorLevelStatus.IN_RANGE: "In range",
        ProcessorLevelStatus.NO_DETECTION: "Not available",
        ProcessorLevelStatus.OVERFLOW: "Warning: Overflow",
        ProcessorLevelStatus.OUT_OF_RANGE: "Out of range",
    }

    def __init__(
        self,
        config: RefAppConfig,
        num_curves: int,
    ) -> None:
        self.num_curves = num_curves
        self.start_m = config.start_m
        self.end_m = config.end_m

    def setup(self, win):
        # Sweep plot
        self.sweep_plot = win.addPlot(row=1, col=0, colspan=3)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        self.vertical_line_start = pg.InfiniteLine(
            pen=et.utils.pg_pen_cycler(2),
            label="Tank start",
            labelOpts={
                "position": 0.5,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.sweep_plot.addItem(self.vertical_line_start)
        self.vertical_line_end = pg.InfiniteLine(
            pen=et.utils.pg_pen_cycler(2),
            label="Tank end",
            labelOpts={
                "position": 0.5,
                "color": (0, 100, 0),
                "fill": (200, 200, 200, 50),
                "movable": True,
            },
        )
        self.sweep_plot.addItem(self.vertical_line_end)

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.sweep_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

        pen = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.threshold_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweep_curves[0], "Sweep")
        sweep_plot_legend.addItem(self.threshold_curves[0], "Threshold")

        # Level history plot
        self.level_history_plot = win.addPlot(row=0, col=1, colspan=2)
        self.level_history_plot.setMenuEnabled(False)
        self.level_history_plot.showGrid(x=True, y=True)
        self.level_history_plot.addLegend()
        self.level_history_plot.setLabel("left", "Estimated level (cm)")
        self.level_history_plot.setLabel("bottom", "Time (s)")
        self.level_history_plot.addItem(pg.PlotDataItem())

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.level_history_curve = self.level_history_plot.plot(**feat_kw)

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits()

        # text items
        self.level_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:12pt;">'
            "{}</span></div>"
        )

        self.level_text_item = pg.TextItem(
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )
        self.level_history_plot.addItem(self.level_text_item)
        self.level_text_item.hide()

    def update(
        self,
        result: RefAppResult,
    ) -> None:
        # Get the first element as the plugin only supports single sensor operation.
        (detector_result,) = list(result.extra_result.detector_result.values())
        assert detector_result.distances is not None

        time_and_level_dict = (
            result.extra_result.processor_extra_result.level_and_time_for_plotting
        )

        # clear sweep curves
        for idx in range(len(self.sweep_curves)):
            self.sweep_curves[idx].clear()
            self.threshold_curves[idx].clear()
        # update sweep plot
        max_val_in_plot = 0
        for idx, processor_result in enumerate(detector_result.processor_results):
            assert processor_result.extra_result.used_threshold is not None
            assert processor_result.extra_result.distances_m is not None
            assert processor_result.extra_result.abs_sweep is not None

            self.sweep_curves[idx].setData(
                processor_result.extra_result.distances_m, processor_result.extra_result.abs_sweep
            )

            self.threshold_curves[idx].setData(
                processor_result.extra_result.distances_m,
                processor_result.extra_result.used_threshold,
            )

            max_val_in_subsweep = max(
                max(processor_result.extra_result.used_threshold),
                max(processor_result.extra_result.abs_sweep),
            )

            max_val_in_plot = max(max_val_in_plot, max_val_in_subsweep)

        self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_plot))
        self.vertical_line_start.setValue(self.start_m)
        self.vertical_line_end.setValue(self.end_m)
        self.vertical_line_start.show()
        self.vertical_line_end.show()

        # update level history plot
        if any(~np.isnan(time_and_level_dict["level"])):
            self.level_history_curve.setData(
                time_and_level_dict["time"], time_and_level_dict["level"] * 100
            )
        self.level_history_plot.setXRange(-TIME_HISTORY_S + 1, 0)
        self.level_history_plot.setYRange(0, (self.end_m - self.start_m + 0.01) * 100)

        # update level plot
        if (
            result.level is not None
            and result.peak_detected is not None
            and result.peak_status is not None
        ):
            current_level = result.level
            peak_detected = result.peak_detected
            peak_status = result.peak_status
            level_text = self.STATUS_MSG_MAP[peak_status]
            if peak_detected:
                level_text = "Level: {:.1f} cm, {:.0f} %".format(
                    current_level * 100,
                    current_level / (self.end_m - self.start_m) * 100,
                )

                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)

                x_pos = -(TIME_HISTORY_S) / 2
                y_max_cm = self.end_m * 100
                self.level_text_item.setPos(x_pos, 0.95 * y_max_cm)
                self.level_text_item.show()

            else:
                self.level_text_item.hide()


if __name__ == "__main__":
    main()
