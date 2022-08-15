# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import (
    Aggregator,
    AggregatorConfig,
    AggregatorResult,
    ProcessorConfig,
    ProcessorMode,
    ProcessorSpec,
    ThresholdMethod,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    sensor_id = 1

    sensor_config_1 = a121.SensorConfig(
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
            a121.SubsweepConfig(
                start_point=200,
                step_length=4,
                num_points=50,
                profile=a121.Profile.PROFILE_2,
                hwaas=20,
                phase_enhancement=True,
            ),
        ],
        sweeps_per_frame=1,
    )

    sensor_config_2 = a121.SensorConfig(
        profile=a121.Profile.PROFILE_2,
        start_point=350,
        step_length=4,
        num_points=25,
        phase_enhancement=True,
        sweeps_per_frame=10,
    )

    session_config = a121.SessionConfig(
        [{sensor_id: sensor_config_1}, {sensor_id: sensor_config_2}], extended=True
    )
    extended_metadata = client.setup_session(session_config)

    aggregator_config = AggregatorConfig()

    processor_config = ProcessorConfig(
        processor_mode=ProcessorMode.DISTANCE_ESTIMATION,
        threshold_method=ThresholdMethod.FIXED,
        fixed_threshold_value=500,
    )

    processor_specs = [
        ProcessorSpec(
            processor_config=processor_config,
            group_index=0,
            sensor_id=sensor_id,
            subsweep_indexes=[0, 1],
        ),
        ProcessorSpec(
            processor_config=processor_config,
            group_index=0,
            sensor_id=sensor_id,
            subsweep_indexes=[2],
        ),
        ProcessorSpec(
            processor_config=processor_config,
            group_index=1,
            sensor_id=sensor_id,
            subsweep_indexes=[0],
        ),
    ]

    aggregator = Aggregator(
        session_config=session_config,
        extended_metadata=extended_metadata,
        config=aggregator_config,
        specs=processor_specs,
    )

    pg_updater = PGUpdater(num_sweeps=len(processor_specs))
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        extended_result = client.get_next()
        processed_data = aggregator.process(extended_result)
        try:
            pg_process.put_data(processed_data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    client.disconnect()


class PGUpdater:
    def __init__(self, num_sweeps: int):
        self.num_sweeps = num_sweeps

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
        self.sweep_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_sweeps)]

        pen = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.threshold_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_sweeps)]

    def update(self, result: AggregatorResult):

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


if __name__ == "__main__":
    main()
