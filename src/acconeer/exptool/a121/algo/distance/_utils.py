# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import copy

from acconeer.exptool import a121


def get_calibrate_offset_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        start_point=-30,
        num_points=50,
        step_length=1,
        profile=a121.Profile.PROFILE_1,
        hwaas=64,
        sweeps_per_frame=1,
        enable_loopback=True,
        phase_enhancement=True,
        iq_imbalance_compensation=True,
    )


def get_calibrate_noise_session_config(
    session_config: a121.SessionConfig, sensor_ids: list[int]
) -> a121.SessionConfig:
    noise_session_config = copy.deepcopy(session_config)

    for sensor_id in sensor_ids:
        for group in noise_session_config.groups:
            group[sensor_id].sweeps_per_frame = 1
            # Set num_points to a high number to get sufficient number of data points to
            # estimate the standard deviation. Extra num_points for step_length = 1 together
            # with profile = 5 due to filter margin and cropping
            if any(
                ss.step_length == 1 and ss.profile == a121.Profile.PROFILE_5
                for ss in group[sensor_id].subsweeps
            ):
                num_points = 352
            else:
                num_points = 220
            for subsweep in group[sensor_id].subsweeps:
                subsweep.enable_tx = False
                subsweep.step_length = 1
                subsweep.start_point = 0
                subsweep.num_points = num_points

    return noise_session_config
