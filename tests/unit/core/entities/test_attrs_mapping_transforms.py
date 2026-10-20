# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin


@pytest.mark.parametrize(
    "instance",
    [
        a2.ServerInfo(
            rss_version="a211-version",
            ticks_per_second=1,
            hardware_name="hw",
            sensor_serial="sensor_serial",
            max_baudrate=2,
        ),
        a2.ServerInfo(
            rss_version="a2-version",
            ticks_per_second=1,
            hardware_name="hw",
            sensor_serial="sensor_serial",
            max_baudrate=2,
        ),
        a2.SubsweepConfig(num_points=42),
        a2.SensorConfig(
            subsweeps=[
                a2.SubsweepConfig(num_points=42),
                a2.SubsweepConfig(num_points=24),
            ],
            sweeps_per_frame=5,
            sweep_rate=10.0,
            frame_rate=14.0,
            inter_frame_idle_state=a2.IdleState.READY,
            inter_sweep_idle_state=a2.IdleState.READY,
        ),
        a2.SessionConfig(
            sensor_configs=[
                a2.SensorConfig.identical_subsweeps(num_subsweeps=3, num_points=5),
                a2.SensorConfig.default(),
            ],
            update_rate=None,
        ),
    ],
)
def test_encode_decode_equality(instance: AttrsMappingTransformsMixin) -> None:
    assert instance == type(instance).from_dict(instance.to_dict())
    assert instance == type(instance).from_json(instance.to_json())
