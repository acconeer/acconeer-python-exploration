# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo.vibration import (
    ExampleApp,
    ExampleAppConfig,
    ExampleAppResult,
    get_high_frequency_config,
)
from acconeer.exptool.a121.algo.vibration.plot import VibrationPlot


SENSOR_ID = 1


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    example_app_config = get_high_frequency_config()

    client = a121.Client.open(**a121.get_client_args(args))

    example_app = ExampleApp(
        client=client,
        sensor_id=SENSOR_ID,
        example_app_config=example_app_config,
    )

    pg_updater = PGUpdater(example_app_config)
    pg_process = et.PGProcess(pg_updater)

    example_app.start()
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        example_app_result = example_app.get_next()

        try:
            pg_process.put_data(example_app_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    example_app.stop()


class PGUpdater:
    def __init__(self, example_app_config: ExampleAppConfig) -> None:
        self._sensor_config = ExampleApp._get_sensor_config(example_app_config)
        self._meas_dist_m = example_app_config.measured_point * APPROX_BASE_STEP_LENGTH_M
        self._vibration_plot = VibrationPlot()

    def setup(self, win: pg.GraphicsLayoutWidget) -> None:
        self._vibration_plot.setup_plot(win, self._meas_dist_m)

    def update(self, example_app_result: ExampleAppResult) -> None:
        self._vibration_plot.update_plot(
            result=example_app_result,
            extra_result=example_app_result.processor_extra_result,
            show_time_series_std=True,
        )


if __name__ == "__main__":
    main()
