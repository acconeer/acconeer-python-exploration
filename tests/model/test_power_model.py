# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import typing as t
from pathlib import Path

import pytest
import yaml

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import distance, presence
from acconeer.exptool.a121.algo.presence import _configs as presence_configs
from acconeer.exptool.a121.model import power


@pytest.fixture
def sensor_current_limits(sensor_current_limits_path: Path) -> t.Iterator[dict[str, t.Any]]:
    with sensor_current_limits_path.open("r") as f:
        yield yaml.safe_load(f)


@pytest.fixture
def module_current_limits(module_current_limits_path: Path) -> t.Iterator[dict[str, t.Any]]:
    with module_current_limits_path.open("r") as f:
        yield yaml.safe_load(f)


@pytest.fixture
def inter_sweep_idle_state_limits(
    inter_sweep_idle_state_current_limits_path: Path,
) -> t.Iterator[dict[str, t.Any]]:
    with inter_sweep_idle_state_current_limits_path.open("r") as f:
        yield yaml.safe_load(f)


def _assert_percent_off_message(actual: float, expected: float, absolute_tolerance: float) -> None:
    percent_off = actual / expected - 1

    if percent_off < 0:
        message = f"Model underestimated by {-percent_off:.2%}"
    else:
        message = f"Model overestimated by {percent_off:.2%}"

    assert actual == pytest.approx(expected, abs=absolute_tolerance), message


@pytest.mark.parametrize(
    ("limit_name", "actual"),
    [
        (
            "Idle state, deep_sleep",
            power.frame_idle(
                a121.IdleState.DEEP_SLEEP, duration=1, module=power.Module.none()
            ).average_current,
        ),
        (
            "Idle state, sleep",
            power.frame_idle(
                a121.IdleState.SLEEP, duration=1, module=power.Module.none()
            ).average_current,
        ),
        (
            "Idle state, ready",
            power.frame_idle(
                a121.IdleState.READY, duration=1, module=power.Module.none()
            ).average_current,
        ),
        (
            "Measurement state, profile 1",
            power.subsweep_active(
                a121.SubsweepConfig(profile=a121.Profile.PROFILE_1),
                high_speed_mode=False,
                subsweep_index=0,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "Measurement state, profile 2",
            power.subsweep_active(
                a121.SubsweepConfig(profile=a121.Profile.PROFILE_2),
                high_speed_mode=False,
                subsweep_index=0,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "Measurement state, profile 3",
            power.subsweep_active(
                a121.SubsweepConfig(profile=a121.Profile.PROFILE_3),
                high_speed_mode=False,
                subsweep_index=0,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "Measurement state, profile 4",
            power.subsweep_active(
                a121.SubsweepConfig(profile=a121.Profile.PROFILE_4),
                high_speed_mode=False,
                subsweep_index=0,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "Measurement state, profile 5",
            power.subsweep_active(
                a121.SubsweepConfig(profile=a121.Profile.PROFILE_5),
                high_speed_mode=False,
                subsweep_index=0,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "Hibernation state",
            power.power_state(
                power.Sensor.IdleState.HIBERNATE, duration=1, module=power.Module.none()
            ).average_current,
        ),
        (
            "Off state, ENABLE low",
            power.power_state(
                power.Sensor.IdleState.OFF, duration=1, module=power.Module.none()
            ).average_current,
        ),
    ],
)
def test_sensor_current_limits(
    sensor_current_limits: dict[str, dict[str, float]], limit_name: str, actual: float
) -> None:
    unit_factor = 1e-3

    expected_current = sensor_current_limits[limit_name]["target"] * unit_factor
    absolute_tolerance = sensor_current_limits[limit_name]["abs_tol"] * unit_factor

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("limit_name", "actual"),
    [
        (
            "deep_sleep",
            power.sweep_idle(
                a121.SensorConfig(inter_sweep_idle_state=a121.IdleState.DEEP_SLEEP),
                duration=1,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "ready",
            power.sweep_idle(
                a121.SensorConfig(inter_sweep_idle_state=a121.IdleState.READY),
                duration=1,
                module=power.Module.none(),
            ).average_current,
        ),
        (
            "sleep",
            power.sweep_idle(
                a121.SensorConfig(inter_sweep_idle_state=a121.IdleState.SLEEP),
                duration=1,
                module=power.Module.none(),
            ).average_current,
        ),
    ],
)
def test_inter_sweep_idle_state_current_limits(
    inter_sweep_idle_state_limits: dict[str, t.Any],
    limit_name: str,
    actual: float,
) -> None:
    unit_factor = 1e-3

    expected_current = inter_sweep_idle_state_limits[limit_name]["target"] * unit_factor
    absolute_tolerance = inter_sweep_idle_state_limits[limit_name]["abs_tol"] * unit_factor

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("limit_name", "lower_idle_state"),
    [
        ("Off state, ENABLE low", power.Sensor.IdleState.OFF),
        ("Hibernation state", power.Sensor.IdleState.HIBERNATE),
    ],
)
def test_lower_idle_state_limits(
    module_current_limits: dict[str, t.Any],
    limit_name: str,
    lower_idle_state: power.Sensor.LowerIdleState,
) -> None:
    unit = module_current_limits[limit_name]["limits"]["xm125"]["unit"]
    unit_factor = {"mA": 1e-3, "μA": 1e-6}[unit]

    expected_current = module_current_limits[limit_name]["limits"]["xm125"]["target"] * unit_factor
    absolute_tolerance = (
        module_current_limits[limit_name]["limits"]["xm125"]["abs_tol"] * unit_factor
    )

    avg_current = power.power_state(lower_idle_state, duration=0.1).average_current
    assert avg_current == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("limit_name", "session_config", "lower_idle_state", "algorithm"),
    [
        (
            "Distance, Default",
            distance.detector_config_to_session_config(
                distance.DetectorConfig(update_rate=1.0, close_range_leakage_cancellation=True),
                sensor_ids=[1],
            ),
            power.Sensor.IdleState.OFF,
            power.algo.Distance(),
        ),
        (
            "Distance, Close",
            distance.detector_config_to_session_config(
                distance.DetectorConfig(
                    start_m=0.05,
                    end_m=0.10,
                    update_rate=1.0,
                    close_range_leakage_cancellation=False,
                ),
                sensor_ids=[1],
            ),
            power.Sensor.IdleState.OFF,
            power.algo.Distance(),
        ),
        (
            "Distance, Close and far",
            distance.detector_config_to_session_config(
                distance.DetectorConfig(
                    start_m=0.05,
                    end_m=3.0,
                    update_rate=1.0,
                    close_range_leakage_cancellation=False,
                ),
                sensor_ids=[1],
            ),
            power.Sensor.IdleState.OFF,
            power.algo.Distance(),
        ),
        (
            "Distance, Far",
            distance.detector_config_to_session_config(
                distance.DetectorConfig(
                    start_m=0.25,
                    end_m=3.0,
                    update_rate=1.0,
                ),
                sensor_ids=[1],
            ),
            power.Sensor.IdleState.OFF,
            power.algo.Distance(),
        ),
        (
            "Presence, Medium range (12Hz)",
            a121.SessionConfig(
                presence.Detector._get_sensor_config(presence_configs.get_medium_range_config()),
            ),
            power.Sensor.IdleState.HIBERNATE,
            power.algo.Presence(),
        ),
        (
            "Presence, Short range (10Hz)",
            a121.SessionConfig(
                presence.Detector._get_sensor_config(presence_configs.get_short_range_config()),
            ),
            power.Sensor.IdleState.HIBERNATE,
            power.algo.Presence(),
        ),
        (
            "Presence, Low Power Wakeup (1Hz)",
            a121.SessionConfig(
                presence.Detector._get_sensor_config(presence_configs.get_low_power_config()),
            ),
            power.Sensor.IdleState.HIBERNATE,
            power.algo.Presence(),
        ),
    ],
)
def test_module_limits(
    module_current_limits: dict[str, t.Any],
    limit_name: str,
    session_config: a121.SessionConfig,
    lower_idle_state: power.Sensor.LowerIdleState,
    algorithm: power.algo.Algorithm,
) -> None:
    unit = module_current_limits[limit_name]["limits"]["xm125"]["unit"]
    unit_factor = {"mA": 1e-3, "μA": 1e-6}[unit]

    expected_current = module_current_limits[limit_name]["limits"]["xm125"]["target"] * unit_factor
    absolute_tolerance = (
        module_current_limits[limit_name]["limits"]["xm125"]["abs_tol"] * unit_factor
    )

    avg_current = power.converged_average_current(
        session_config,
        lower_idle_state,
        absolute_tolerance / 4,
        algorithm=algorithm,
    )
    _assert_percent_off_message(avg_current, expected_current, absolute_tolerance)
