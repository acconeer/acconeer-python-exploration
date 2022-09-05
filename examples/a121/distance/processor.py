# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import copy

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorMode,
    ThresholdMethod,
    calculate_bg_noise_std,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    # Define sensor configuration.
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                start_point=50,
                step_length=4,
                num_points=50,
                profile=a121.Profile.PROFILE_1,
                hwaas=32,
                phase_enhancement=True,
            )
        ],
        sweeps_per_frame=1,
    )

    # Calibrate noise.
    noise_sensor_config = copy.deepcopy(sensor_config)
    for subsweep in noise_sensor_config.subsweeps:
        # Disable Tx when measuring background noise.
        subsweep.enable_tx = False

    metadata = client.setup_session(noise_sensor_config)
    client.start_session()
    result = client.get_next()
    client.stop_session()

    stds = [
        calculate_bg_noise_std(subframe, subsweep_config)
        for (subframe, subsweep_config) in zip(result.subframes, noise_sensor_config.subsweeps)
    ]

    # Create processor for distance estimation.
    distance_context = ProcessorContext(
        bg_noise_std=stds,
    )
    distance_config = ProcessorConfig(
        processor_mode=ProcessorMode.DISTANCE_ESTIMATION,
        threshold_method=ThresholdMethod.CFAR,
        threshold_sensitivity=0.8,
    )
    distance_processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=distance_config,
        context=distance_context,
    )

    pg_updater = PGUpdater()
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    metadata = client.setup_session(sensor_config)
    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        extended_result = client.get_next()
        processed_data = distance_processor.process(extended_result)
        try:
            pg_process.put_data(processed_data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(self):
        self.history = [np.NaN] * 100

    def setup(self, win):
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance(m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        legends = ["Sweep", "Threshold"]
        self.curves = {}
        for i, legend in enumerate(legends):
            pen = et.utils.pg_pen_cycler(i)
            brush = et.utils.pg_brush_cycler(i)
            symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
            feat_kw = dict(pen=pen, **symbol_kw)
            self.curves[legend] = self.sweep_plot.plot(**feat_kw, name=legends[i])

        self.smooth_max = et.utils.SmoothMax()

        self.dist_history_plot = win.addPlot(row=1, col=0)
        self.dist_history_plot.setMenuEnabled(False)
        self.dist_history_plot.showGrid(x=True, y=True)
        self.dist_history_plot.addLegend()
        self.dist_history_plot.setLabel("left", "Estimated distance (m)")
        self.dist_history_plot.setLabel("bottom", "History (frame)")
        self.dist_history_plot.addItem(pg.PlotDataItem())
        self.dist_history_plot.setXRange(0, len(self.history))

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.dist_history_curve = self.dist_history_plot.plot(**feat_kw)

    def update(self, d):
        sweep = d.extra_result.abs_sweep
        threshold = d.extra_result.used_threshold
        distances = d.extra_result.distances_m

        self.history.pop(0)
        if len(d.estimated_distances) != 0:
            self.history.append(d.estimated_distances[0])
        else:
            self.history.append(np.nan)

        self.curves["Sweep"].setData(distances, sweep)
        self.curves["Threshold"].setData(distances, threshold)
        self.sweep_plot.setYRange(
            0,
            self.smooth_max.update(np.amax(np.concatenate((sweep, threshold)))),
        )

        if not np.all(np.isnan(self.history)):
            self.dist_history_curve.setData(self.history)


if __name__ == "__main__":
    main()
