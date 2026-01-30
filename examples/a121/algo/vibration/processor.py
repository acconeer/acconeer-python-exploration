# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo.vibration import (
    ExampleApp,
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
    get_high_frequency_config,
)
from acconeer.exptool.a121.algo.vibration._processor import RANGE_SUBSWEEP
from acconeer.exptool.a121.algo.vibration.plot import VibrationPlot


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    sensor_config = ExampleApp._get_sensor_config(get_high_frequency_config())

    client = a121.Client.open(**a121.get_client_args(args))
    metadata = client.setup_session(sensor_config)

    processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=ProcessorConfig(),
        context=ProcessorContext(),
    )
    pg_updater = PGUpdater(sensor_config)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()
    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        plot_data = processor.process(result)
        try:
            pg_process.put_data(plot_data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    client.close()


class PGUpdater:
    def __init__(self, sensor_config: a121.SensorConfig) -> None:
        self._sensor_config = sensor_config.subsweeps[RANGE_SUBSWEEP]
        self._meas_dist_m = self._sensor_config.start_point * APPROX_BASE_STEP_LENGTH_M
        self._vibration_plot = VibrationPlot()

    def setup(self, win: pg.GraphicsLayoutWidget) -> None:
        self._vibration_plot.setup_plot(win, self._meas_dist_m)

    def update(self, processor_result: ProcessorResult) -> None:
        self._vibration_plot.update_plot(
            result=processor_result,
            extra_result=processor_result.extra_result,
            show_time_series_std=True,
        )


if __name__ == "__main__":
    main()
