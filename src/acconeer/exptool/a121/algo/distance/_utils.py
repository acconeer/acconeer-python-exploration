# Copyright (c) Acconeer AB, 2024-2025
# All rights reserved

from __future__ import annotations

import copy
from typing import List

import attrs

from acconeer.exptool import a121

from ._aggregator import ProcessorSpec
from ._processors import MeasurementType, ProcessorMode


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
    session_config: a121.SessionConfig, sensor_ids: List[int]
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


def update_processor_mode(
    processor_specs: list[ProcessorSpec], processor_mode: ProcessorMode
) -> list[ProcessorSpec]:
    updated_specs = []
    for spec in processor_specs:
        new_processor_config = attrs.evolve(spec.processor_config, processor_mode=processor_mode)
        updated_specs.append(attrs.evolve(spec, processor_config=new_processor_config))
    return updated_specs


def filter_close_range_spec(specs: list[ProcessorSpec]) -> list[ProcessorSpec]:
    NUM_CLOSE_RANGE_SPECS = 1
    close_range_specs = []
    for spec in specs:
        if spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            close_range_specs.append(spec)
    if len(close_range_specs) != NUM_CLOSE_RANGE_SPECS:
        msg = "Incorrect subsweep config for close range measurement"
        raise ValueError(msg)

    return close_range_specs
