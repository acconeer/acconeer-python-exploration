# Copyright (c) Acconeer AB, 2026
# All rights reserved

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance._views import (
    RangeSweepConfig,
)


def test_range_sweep_config_initialization() -> None:
    # Should succeed for valid sensor config
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=100,
                num_points=3,
                step_length=2,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=106,
                num_points=4,
                step_length=2,
                phase_enhancement=True,
            ),
        ],
    )
    range_sweep_config = RangeSweepConfig.from_sensor_config(sensor_config)
    assert range_sweep_config.num_subsweeps == 2
    assert range_sweep_config.start_point == 100
    assert range_sweep_config.num_points == 7

    # Should fail if phase enhancement is not enabled in all subsweeps
    with pytest.raises(ValueError, match="Phase enhancement must be enabled"):
        sensor_config = a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(
                    profile=a121.Profile.PROFILE_1,
                    phase_enhancement=False,
                ),
            ],
        )
        RangeSweepConfig.from_sensor_config(sensor_config)

    # Should fail if subsweeps are not contiguous
    with pytest.raises(ValueError, match="Subsweeps used for range processing must be contiguous"):
        sensor_config = a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(
                    profile=a121.Profile.PROFILE_1,
                    start_point=0,
                    num_points=100,
                    phase_enhancement=True,
                ),
                a121.SubsweepConfig(
                    profile=a121.Profile.PROFILE_1,
                    start_point=200,
                    num_points=100,
                    phase_enhancement=True,
                ),
            ],
        )
        RangeSweepConfig.from_sensor_config(sensor_config)

    # Should fail if subsweeps do not have the same profile
    with pytest.raises(ValueError, match="Expected same profile for all subsweeps"):
        sensor_config = a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(
                    profile=a121.Profile.PROFILE_2,
                    start_point=0,
                    num_points=100,
                    step_length=1,
                    phase_enhancement=True,
                ),
                a121.SubsweepConfig(
                    profile=a121.Profile.PROFILE_2,
                    start_point=100,
                    num_points=100,
                    step_length=1,
                    phase_enhancement=True,
                ),
                a121.SubsweepConfig(
                    profile=a121.Profile.PROFILE_3,
                    start_point=200,
                    num_points=100,
                    step_length=1,
                    phase_enhancement=True,
                ),
            ],
        )
        RangeSweepConfig.from_sensor_config(sensor_config)

    # Should fail if subsweeps do not have the same step length
    with pytest.raises(ValueError, match="Expected same step length for all subsweeps"):
        sensor_config = a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(
                    start_point=100,
                    num_points=3,
                    step_length=2,
                    phase_enhancement=True,
                ),
                a121.SubsweepConfig(
                    start_point=106,
                    num_points=4,
                    step_length=4,
                    phase_enhancement=True,
                ),
            ],
        )
        RangeSweepConfig.from_sensor_config(sensor_config)


def test_range_sweep_config_profile() -> None:
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_2,
                start_point=100,
                num_points=50,
                step_length=1,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_2,
                start_point=150,
                num_points=50,
                step_length=1,
                phase_enhancement=True,
            ),
        ],
    )

    range_sweep_config = RangeSweepConfig.from_sensor_config(sensor_config)
    actual_profile = range_sweep_config.profile
    expected_profile = a121.Profile.PROFILE_2
    assert actual_profile == expected_profile


def test_range_sweep_config_start_point() -> None:
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=100,
                num_points=50,
                step_length=1,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=150,
                num_points=50,
                step_length=1,
                phase_enhancement=True,
            ),
        ],
    )

    range_sweep_config = RangeSweepConfig.from_sensor_config(sensor_config)
    actual_start_point = range_sweep_config.start_point
    expected_start_point = 100
    assert actual_start_point == expected_start_point


def test_range_sweep_config_num_points() -> None:
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=100,
                num_points=100,
                step_length=1,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=200,
                num_points=150,
                step_length=1,
                phase_enhancement=True,
            ),
        ],
    )

    range_sweep_config = RangeSweepConfig.from_sensor_config(sensor_config)
    actual_num_points = range_sweep_config.num_points
    expected_num_points = 250
    assert actual_num_points == expected_num_points


def test_range_sweep_config_subsweep_slices() -> None:
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=100,
                num_points=3,
                step_length=2,
                phase_enhancement=True,
            ),
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_5,
                start_point=106,
                num_points=4,
                step_length=2,
                phase_enhancement=True,
            ),
        ],
    )

    range_sweep_config = RangeSweepConfig.from_sensor_config(sensor_config)
    subsweep_slices = range_sweep_config.subsweep_slices

    # Full slices should be defined by the subsweep start points and number of points
    actual_slices = subsweep_slices.full
    expected_slices = [slice(0, 3, 1), slice(3, 7, 1)]
    assert actual_slices == expected_slices

    # Valid slices should be masked by the specified edge margin
    actual_slices = subsweep_slices.valid(edge_margin=1)
    expected_slices = [slice(1, 3, 1), slice(3, 6, 1)]
    assert actual_slices == expected_slices

    # Cropped slices should be adjusted to the cropped range sweep
    actual_slices = subsweep_slices.cropped(edge_margin=1)
    expected_slices = [slice(0, 2, 1), slice(2, 5, 1)]
    assert actual_slices == expected_slices
