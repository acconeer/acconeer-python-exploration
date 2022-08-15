# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

import acconeer.exptool as et
from acconeer.exptool import a121


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    session_config = a121.SessionConfig(
        [
            {
                1: a121.SensorConfig(
                    subsweeps=[
                        a121.SubsweepConfig(
                            start_point=25,
                            step_length=2,
                            num_points=30,
                            profile=a121.Profile.PROFILE_1,
                            hwaas=10,
                        ),
                        a121.SubsweepConfig(
                            start_point=75,
                            step_length=4,
                            num_points=25,
                            profile=a121.Profile.PROFILE_3,
                            hwaas=20,
                        ),
                    ],
                )
            },
            {
                1: a121.SensorConfig(
                    receiver_gain=20,
                ),
            },
        ],
        extended=True,
    )

    extended_metadata = client.setup_session(session_config)

    pg_updater = PGUpdater(session_config, extended_metadata)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        extended_result = client.get_next()

        try:
            pg_process.put_data(extended_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:
    def __init__(
        self,
        session_config: a121.SessionConfig,
        extended_metadata: list[dict[int, a121.Metadata]],
    ) -> None:
        self.session_config = session_config
        self.extended_metadata = extended_metadata

    def setup(self, win):
        self.all_plots = []
        self.all_curves = []
        self.all_smooth_maxs = []

        for group_idx, group in enumerate(self.session_config.groups):
            group_plots = {}
            group_curves = {}
            group_smooth_maxs = {}

            for sensor_id, sensor_config in group.items():
                title = f"Group {group_idx} / Sensor {sensor_id}"
                plot = win.addPlot(title=title)
                plot.setMenuEnabled(False)
                plot.setMouseEnabled(x=False, y=False)
                plot.hideButtons()
                plot.showGrid(x=True, y=True)

                plot.setLabel("bottom", "Depth (m)")
                plot.setLabel("left", "Amplitude")

                curves = []
                for i in range(sensor_config.num_subsweeps):
                    curve = plot.plot(pen=et.utils.pg_pen_cycler(i))
                    curves.append(curve)

                group_plots[sensor_id] = plot
                group_curves[sensor_id] = curves

                smooth_max = et.utils.SmoothMax(self.session_config.update_rate)
                group_smooth_maxs[sensor_id] = smooth_max

            self.all_plots.append(group_plots)
            self.all_curves.append(group_curves)
            self.all_smooth_maxs.append(group_smooth_maxs)

    def update(self, extended_result: list[dict[int, a121.Result]]) -> None:
        for group_idx, group in enumerate(extended_result):
            for sensor_id, result in group.items():
                plot = self.all_plots[group_idx][sensor_id]
                curves = self.all_curves[group_idx][sensor_id]

                max_ = 0

                for sub_idx, subframe in enumerate(result.subframes):
                    x = get_distances_m(
                        self.session_config.groups[group_idx][sensor_id].subsweeps[sub_idx]
                    )
                    y = np.abs(subframe).mean(axis=0)
                    curves[sub_idx].setData(x, y)

                    max_ = max(max_, np.max(y))

                smooth_max = self.all_smooth_maxs[group_idx][sensor_id]
                plot.setYRange(0, smooth_max.update(max_))


def get_distances_m(config):
    range_p = np.arange(config.num_points) * config.step_length + config.start_point
    return range_p * 2.5e-3


if __name__ == "__main__":
    main()
