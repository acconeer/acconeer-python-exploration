# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

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
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                start_point=50,
                step_length=4,
                num_points=25,
                profile=a121.Profile.PROFILE_1,
                hwaas=10,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                start_point=150,
                step_length=4,
                num_points=25,
                profile=a121.Profile.PROFILE_1,
                hwaas=20,
                phase_enhancement=True,
            ),
        ],
        sweeps_per_frame=5,
    )

    metadata = client.setup_session(sensor_config)

    threshold_config = ProcessorConfig(
        processor_mode=ProcessorMode.RECORDED_THRESHOLD_CALIBRATION,
        threshold_method=ThresholdMethod.RECORDED,
    )
    threshold_processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=threshold_config,
    )

    pg_updater = PGUpdater(None)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    sc_bg_num_sweeps = 20

    for _ in range(sc_bg_num_sweeps):
        result = client.get_next()
        processed_data = threshold_processor.process(result)

    distance_context = ProcessorContext(recorded_threshold=processed_data.recorded_threshold)
    distance_config = ProcessorConfig(
        processor_mode=ProcessorMode.DISTANCE_ESTIMATION, threshold_method=ThresholdMethod.CFAR
    )
    distance_processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=distance_config,
        context=distance_context,
    )

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
    def __init__(self, processing_config):
        self.processing_config = processing_config

    def setup(self, win):
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
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

    def update(self, d):
        threshold = d.extra_result.used_threshold
        valid_threshold_idx = np.where(~np.isnan(threshold))[0]
        threshold = threshold[valid_threshold_idx]

        self.curves["Sweep"].setData(d.extra_result.abs_sweep)
        self.curves["Threshold"].setData(valid_threshold_idx, threshold)
        self.sweep_plot.setYRange(
            0,
            self.smooth_max.update(np.amax(np.concatenate((d.extra_result.abs_sweep, threshold)))),
        )


if __name__ == "__main__":
    main()
