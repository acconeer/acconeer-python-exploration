# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import Detector, DetectorConfig, ThresholdMethod


SENSOR_ID = 1


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()
    detector_config = DetectorConfig(
        start_m=0.0,
        end_m=2.0,
        max_profile=a121.Profile.PROFILE_3,
        max_step_length=12,
        threshold_method=ThresholdMethod.RECORDED,
    )
    detector = Detector(client=client, sensor_ids=[SENSOR_ID], detector_config=detector_config)

    detector.calibrate_detector()

    detector.start()

    pg_updater = PGUpdater(num_curves=len(detector.processor_specs))
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        detector_result = detector.get_next()
        try:
            pg_process.put_data(detector_result)
        except et.PGProccessDiedException:
            break

    detector.stop()

    print("Disconnecting...")
    client.disconnect()


class PGUpdater:
    def __init__(self, num_curves):
        self.num_curves = num_curves
        self.distance_history = [np.NaN] * 100

    def setup(self, win):
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.addItem(pg.PlotDataItem())

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

        self.dist_history_plot = win.addPlot(row=1, col=0)
        self.dist_history_plot.setMenuEnabled(False)
        self.dist_history_plot.showGrid(x=True, y=True)
        self.dist_history_plot.addLegend()
        self.dist_history_plot.setLabel("left", "Estimated_distance")
        self.dist_history_plot.addItem(pg.PlotDataItem())

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.dist_history_curve = self.dist_history_plot.plot(**feat_kw)

        self.distance_hist_smooth_lim = et.utils.SmoothLimits()

    def update(self, multi_sensor_result):
        # Get the first element as the example only supports single sensor operation.
        result = multi_sensor_result[SENSOR_ID]
        self.distance_history.pop(0)
        if len(result.distances) != 0:
            self.distance_history.append(result.distances[0])
        else:
            self.distance_history.append(np.nan)

        for idx, processor_result in enumerate(result.processor_results):
            threshold = processor_result.extra_result.used_threshold
            valid_threshold_idx = np.where(~np.isnan(threshold))[0]
            threshold = threshold[valid_threshold_idx]
            self.sweep_curves[idx].setData(
                processor_result.extra_result.distances_m, processor_result.extra_result.abs_sweep
            )
            self.threshold_curves[idx].setData(
                processor_result.extra_result.distances_m[valid_threshold_idx], threshold
            )
        if np.any(~np.isnan(self.distance_history)):
            self.dist_history_curve.setData(self.distance_history)
            lims = self.distance_hist_smooth_lim.update(self.distance_history)
            self.dist_history_plot.setYRange(lims[0], lims[1])
        else:
            self.dist_history_curve.setData([])


if __name__ == "__main__":
    main()
