# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

from __future__ import annotations

import typing as t
from pathlib import Path

import attrs
import pytest
import yaml

from acconeer.exptool import a2
from acconeer.exptool.a2.model import power


@pytest.fixture
def a2_sensor_current_limits(a2_sensor_current_limits_path: Path) -> t.Iterator[dict[str, t.Any]]:
    with a2_sensor_current_limits_path.open("r") as f:
        yield yaml.safe_load(f)


@pytest.fixture
def a2_timing_limits(
    a2_timing_limits_path: Path,
) -> t.Iterator[dict[str, t.Any]]:
    with a2_timing_limits_path.open("r") as f:
        yield yaml.safe_load(f)


@pytest.fixture
def a2_computation_time_limits(
    a2_computation_time_limits_path: Path,
) -> t.Iterator[dict[str, t.Any]]:
    with a2_computation_time_limits_path.open("r") as f:
        yield yaml.safe_load(f)


def _assert_percent_off_message(
    actual: float, expected: float, absolute_tolerance: float, context: str = ""
) -> None:
    percent_off = actual / expected - 1

    if percent_off < 0:
        message = f"Model underestimated by {-percent_off:.2%}"
    else:
        message = f"Model overestimated by {percent_off:.2%}"

    if context:
        message = f"{context}: {message}"

    assert actual == pytest.approx(expected, abs=absolute_tolerance), message


def _measure_average_current(profile: a2.Profile, prf: a2.PRF) -> float:
    return power.subsweep_active(
        a2.SubsweepConfig(profile=profile, prf=prf),
        subsweep_index=0,
        aps_idle_state=power.SensorConstants.ApsIdleState.APS_HF_WFI,
        high_speed_mode=True,
        inter_sweep_idle_state=a2.IdleState.ARMED,
        jitter_comp=False,
    ).average_current


@pytest.mark.parametrize(
    ("limit_name", "profile", "prf", "actual"),
    [
        (
            "aps_hf_wfi_rs_measure",
            int(profile),
            prf.name,
            _measure_average_current(profile, prf),
        )
        for profile, prf in [
            (a2.Profile.PROFILE_1, a2.PRF.PRF_27_7_MHZ),
            (a2.Profile.PROFILE_2, a2.PRF.PRF_27_7_MHZ),
            (a2.Profile.PROFILE_3, a2.PRF.PRF_27_7_MHZ),
            (a2.Profile.PROFILE_4, a2.PRF.PRF_27_7_MHZ),
            (a2.Profile.PROFILE_5, a2.PRF.PRF_27_7_MHZ),
            (a2.Profile.PROFILE_6, a2.PRF.PRF_27_7_MHZ),
            # Profile 7 does not support PRF 27.7 MHz; the limit is at 20.8 MHz
            (a2.Profile.PROFILE_7, a2.PRF.PRF_20_8_MHZ),
        ]
    ],
)
def test_a2_sensor_current_limits_measure(
    a2_sensor_current_limits: dict[str, dict[str, float]],
    limit_name: str,
    profile: int,
    prf: str,
    actual: float,
) -> None:
    unit_factor = 1e-3

    limits = a2_sensor_current_limits["power_tests"][limit_name][25][profile][prf]
    expected_current = limits["target"] * unit_factor
    absolute_tolerance = limits["abs_tol"] * unit_factor

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


def _wfi_measure_total(profile: a2.Profile, prf: a2.PRF) -> float:
    """Modeled total current in the APS HF WFI measure state (A)."""
    sensor_data = power.SensorConstants.default()
    return (
        sensor_data.measure_currents[profile][prf]
        + sensor_data.inter_frame_aps_currents[power.SensorConstants.ApsIdleState.APS_HF_WFI]
    ).total


def test_a2_sensor_current_limits_measure_all_prfs(
    a2_sensor_current_limits: dict[str, dict[str, float]],
) -> None:
    """Check the modeled measure current against every (profile, prf) limit entry.

    Data-driven from the limits file, so new limit entries are picked up
    automatically.
    """
    unit_factor = 1e-3
    checked_profiles = set()

    for profile, prf_limits in a2_sensor_current_limits["power_tests"]["aps_hf_wfi_rs_measure"][
        25
    ].items():
        for prf_name, limits in prf_limits.items():
            actual = _wfi_measure_total(a2.Profile(profile), a2.PRF[prf_name])
            _assert_percent_off_message(
                actual,
                limits["target"] * unit_factor,
                limits["abs_tol"] * unit_factor,
                context=f"aps_hf_wfi_rs_measure profile {profile}, {prf_name}",
            )
            checked_profiles.add(profile)

    assert checked_profiles >= set(range(1, 8))


def test_a2_prf_current_model_matches_limits(
    a2_sensor_current_limits: dict[str, dict[str, float]],
) -> None:
    """Verify the lookup's intercept/slope stay in sync with the limits fit.

    The coefficients are recovered from the evaluated current table, so this
    exercises the public model rather than re-reading the YAML.
    """
    unit_factor = 1e-3
    # Anchor PRFs supported by all profiles
    low_prf, high_prf = a2.PRF.PRF_5_3_MHZ, a2.PRF.PRF_20_8_MHZ
    low_mhz, high_mhz = low_prf.frequency / 1e6, high_prf.frequency / 1e6
    checked_profiles = set()

    for profile, coefficients in a2_sensor_current_limits["power_tests"]["prf_current"][
        25
    ].items():
        low = _wfi_measure_total(a2.Profile(profile), low_prf)
        high = _wfi_measure_total(a2.Profile(profile), high_prf)
        slope = (high - low) / (high_mhz - low_mhz)
        intercept = low - slope * low_mhz

        for name, actual in (("intercept", intercept), ("slope", slope)):
            limits = coefficients[name]
            assert actual == pytest.approx(
                limits["target"] * unit_factor, abs=limits["abs_tol"] * unit_factor
            ), f"prf_current {name} out of tolerance for profile {profile}"
        checked_profiles.add(profile)

    assert checked_profiles >= set(range(1, 8))


@pytest.mark.parametrize(
    ("profile", "rx_channel", "actual"),
    [
        (
            1,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_1][0].total,
        ),
        (
            1,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_1][1].total,
        ),
        (
            1,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_1][2].total,
        ),
        (
            1,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_1][3].total,
        ),
        (
            2,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_2][0].total,
        ),
        (
            2,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_2][1].total,
        ),
        (
            2,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_2][2].total,
        ),
        (
            2,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_2][3].total,
        ),
        (
            3,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_3][0].total,
        ),
        (
            3,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_3][1].total,
        ),
        (
            3,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_3][2].total,
        ),
        (
            3,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_3][3].total,
        ),
        (
            4,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_4][0].total,
        ),
        (
            4,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_4][1].total,
        ),
        (
            4,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_4][2].total,
        ),
        (
            4,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_4][3].total,
        ),
        (
            5,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_5][0].total,
        ),
        (
            5,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_5][1].total,
        ),
        (
            5,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_5][2].total,
        ),
        (
            5,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_5][3].total,
        ),
        (
            6,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_6][0].total,
        ),
        (
            6,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_6][1].total,
        ),
        (
            6,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_6][2].total,
        ),
        (
            6,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_6][3].total,
        ),
        (
            7,
            0,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_7][0].total,
        ),
        (
            7,
            1,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_7][1].total,
        ),
        (
            7,
            2,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_7][2].total,
        ),
        (
            7,
            3,
            power.SensorConstants.default().rx_antenna_current[a2.Profile.PROFILE_7][3].total,
        ),
    ],
)
def test_a2_sensor_current_limits_rx_channels(
    a2_sensor_current_limits: dict[str, dict[str, float]],
    profile: int,
    rx_channel: int,
    actual: float,
) -> None:
    unit_factor = 1e-3

    expected_current = (
        a2_sensor_current_limits["power_tests"]["rx_channel_current"][25][profile][rx_channel][
            "target"
        ]
        * unit_factor
    )
    absolute_tolerance = (
        a2_sensor_current_limits["power_tests"]["rx_channel_current"][25][profile][rx_channel][
            "abs_tol"
        ]
        * unit_factor
    )

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("limit_name", "actual"),
    [
        (
            "sleep_ultra_deep",
            power.SensorConstants.default()
            .inter_frame_aps_currents[power.SensorConstants.ApsSleepState.ULTRA_DEEP_SLEEP]
            .total,
        ),
        (
            "sleep_deep",
            power.SensorConstants.default()
            .inter_frame_aps_currents[power.SensorConstants.ApsSleepState.DEEP_SLEEP]
            .total,
        ),
        (
            "sleep_shallow",
            power.SensorConstants.default()
            .inter_frame_aps_currents[power.SensorConstants.ApsSleepState.SHALLOW_SLEEP]
            .total,
        ),
        (
            "aps_lf_wfi_rs_off",
            power.SensorConstants.default()
            .inter_frame_aps_currents[power.SensorConstants.ApsIdleState.APS_LF_WFI]
            .total,
        ),
        (
            "aps_lf_rs_off",
            power.SensorConstants.default()
            .aps_active_currents[power.SensorConstants.ApsActiveState.APS_LF]
            .total,
        ),
        (
            "aps_mf_wfi_rs_off",
            power.SensorConstants.default()
            .inter_frame_aps_currents[power.SensorConstants.ApsIdleState.APS_MF_WFI]
            .total,
        ),
        (
            "aps_mf_rs_off",
            power.SensorConstants.default()
            .aps_active_currents[power.SensorConstants.ApsActiveState.APS_MF]
            .total,
        ),
        (
            "aps_hf_wfi_rs_off",
            power.SensorConstants.default()
            .inter_frame_aps_currents[power.SensorConstants.ApsIdleState.APS_HF_WFI]
            .total,
        ),
        (
            "aps_hf_wfi_rs_ready_wfi",
            power.SensorConstants.default().idle_currents[a2.IdleState.READY].total,
        ),
        (
            "aps_hf_wfi_rs_armed_wfi",
            power.SensorConstants.default().idle_currents[a2.IdleState.ARMED].total,
        ),
        (
            "aps_hf_rs_off",
            power.SensorConstants.default()
            .aps_active_currents[power.SensorConstants.ApsActiveState.APS_HF]
            .total,
        ),
    ],
)
def test_a2_sensor_current_limits(
    a2_sensor_current_limits: dict[str, dict[str, float]],
    limit_name: str,
    actual: float,
) -> None:
    unit_factor = 1e-3

    expected_current = (
        a2_sensor_current_limits["power_tests"][limit_name][25]["target"] * unit_factor
    )
    absolute_tolerance = (
        a2_sensor_current_limits["power_tests"][limit_name][25]["abs_tol"] * unit_factor
    )

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("configuration", "session_config", "aps_sleep_state", "algorithm"),
    [
        (
            "shallow_sleep",
            a2.SessionConfig(
                sensor_configs=[
                    a2.SensorConfig(
                        subsweeps=[
                            a2.SubsweepConfig(
                                start_point=144,
                                num_points=3,
                                step_length=48,
                                hwaas_max=10,
                                hwaas_min=1,
                                hwaas_exponent=4,
                                profile=a2.Profile.PROFILE_5,
                                prf=a2.PRF.PRF_27_7_MHZ,
                                tx_antenna_mask=0b10,
                                rx_antenna_mask=0b1111,
                            )
                        ],
                        sweeps_per_frame=16,
                        jitter_compensation=False,
                        inter_sweep_idle_state=a2.IdleState.ARMED,
                        inter_frame_idle_state=a2.IdleState.ARMED,
                        sweep_rate=None,
                        frame_rate=None,
                    ),
                ],
                update_rate=2.0,
            ),
            power.SensorConstants.ApsSleepState.SHALLOW_SLEEP,
            power.algo.HeatmapConventional(
                power.algo.HeatmapConventionalConfig(
                    antenna_array=a2.AntennaArray.AP212,
                    heatmap_mode=power.algo.HeatmapConventionalConfig.HeatmapMode.MOVEMENT,
                    covariance_matrix_time_constant_s=0.8,
                    high_pass_filter_time_constant_s=1.0,
                    az_angle_range=(-60.0, 60.0),
                    num_az_angles=25,
                    el_angle_range=(-0.0, 0.0),
                    num_el_angles=1,
                )
            ),
        ),
        (
            "lf_wfi",
            a2.SessionConfig(
                sensor_configs=[
                    a2.SensorConfig(
                        subsweeps=[
                            a2.SubsweepConfig(
                                start_point=144,
                                num_points=3,
                                step_length=48,
                                hwaas_max=10,
                                hwaas_min=1,
                                hwaas_exponent=4,
                                profile=a2.Profile.PROFILE_5,
                                prf=a2.PRF.PRF_27_7_MHZ,
                                tx_antenna_mask=0b10,
                                rx_antenna_mask=0b1111,
                            )
                        ],
                        sweeps_per_frame=16,
                        jitter_compensation=False,
                        inter_sweep_idle_state=a2.IdleState.ARMED,
                        inter_frame_idle_state=a2.IdleState.ARMED,
                        sweep_rate=None,
                        frame_rate=None,
                    ),
                ],
                update_rate=2.0,
            ),
            power.SensorConstants.ApsIdleState.APS_LF_WFI,
            power.algo.HeatmapConventional(
                power.algo.HeatmapConventionalConfig(
                    antenna_array=a2.AntennaArray.AP212,
                    heatmap_mode=power.algo.HeatmapConventionalConfig.HeatmapMode.MOVEMENT,
                    covariance_matrix_time_constant_s=0.8,
                    high_pass_filter_time_constant_s=1.0,
                    az_angle_range=(-60.0, 60.0),
                    num_az_angles=25,
                    el_angle_range=(-0.0, 0.0),
                    num_el_angles=1,
                )
            ),
        ),
    ],
)
def test_example_config_average_current(
    a2_sensor_current_limits: dict[str, dict[str, float]],
    configuration: str,
    session_config: a2.SessionConfig,
    aps_sleep_state: power.SensorConstants.ApsIdleState | power.SensorConstants.ApsSleepState,
    algorithm: power.algo.Algorithm,
) -> None:
    unit_factor = 1e-6

    expected_current = (
        a2_sensor_current_limits["in_cabin_intrusion"][configuration][25]["target"] * unit_factor
    )
    absolute_tolerance = (
        a2_sensor_current_limits["in_cabin_intrusion"][configuration][25]["abs_tol"] * unit_factor
    )

    avg_current = power.converged_average_current(
        session_config,
        aps_sleep_state,
        power.SensorConstants.ApsIdleState.APS_HF_WFI,
        power.SensorConstants.ApsActiveState.APS_HF,
        absolute_tolerance / 4,
        algorithm=algorithm,
    )

    assert avg_current == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("limit_name", "actual"),
    [
        (
            "shallow_boot",
            power.exit_idle(
                a2.SessionConfig(sensor_configs=[a2.SensorConfig.default()], update_rate=1.0),
                power.SensorConstants.ApsSleepState.SHALLOW_SLEEP,
                None,
                None,
            ).duration,
        ),
        (
            "cold_boot_nvm",
            power.exit_idle(
                a2.SessionConfig(sensor_configs=[a2.SensorConfig.default()], update_rate=1.0),
                power.SensorConstants.ApsSleepState.DEEP_SLEEP,
                None,
                None,
            ).duration,
        ),
        (
            "aps_hf_to_lf",
            power.SensorConstants.default().aps_hf_to_lf_state.duration,
        ),
        (
            "aps_hf_to_mf",
            power.SensorConstants.default().aps_hf_to_mf_state.duration,
        ),
        (
            "aps_lf_to_hf",
            power.SensorConstants.default().aps_lf_to_hf_state.duration,
        ),
        (
            "aps_mf_to_hf",
            power.SensorConstants.default().aps_mf_to_hf_state.duration,
        ),
        (
            "radar_power_on",
            power.SensorConstants.default().radar_power_on_state.duration,
        ),
        (
            "radar_power_off",
            power.SensorConstants.default().radar_power_off_state.duration,
        ),
        (
            "radar_prepare",
            power.SensorConstants.default().radar_prepare_state.duration,
        ),
        (
            "radar_prepare_rs_init",
            power.SensorConstants.default().radar_prepare_rs_init_state.duration,
        ),
        (
            "radar_calibration",
            power.SensorConstants.default().calibration_state.duration,
        ),
        (
            "shallow_boot_app_init",
            power.SensorConstants.default()
            .aps_sleep_wakeup_state[power.SensorConstants.ApsSleepState.SHALLOW_SLEEP]
            .duration,
        ),
        (
            "cold_boot_nvm_app_init",
            power.SensorConstants.default()
            .aps_sleep_wakeup_state[power.SensorConstants.ApsSleepState.DEEP_SLEEP]
            .duration,
        ),
    ],
)
def test_a2_timing_limits(
    a2_timing_limits: dict[str, t.Any],
    limit_name: str,
    actual: float,
) -> None:
    unit_factor = 1e-6

    expected_current = a2_timing_limits[limit_name]["gcc"]["target"] * unit_factor
    absolute_tolerance = a2_timing_limits[limit_name]["gcc"]["abs_tol"] * unit_factor

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("configuration", "actual"),
    [
        (
            "frame_duration_conf1",
            power.frame_active(
                a2.SessionConfig(
                    sensor_configs=[
                        a2.SensorConfig(
                            subsweeps=[
                                a2.SubsweepConfig(
                                    start_point=100,
                                    num_points=10,
                                    step_length=1,
                                    hwaas_max=100,
                                    profile=a2.Profile.PROFILE_3,
                                    prf=a2.PRF.PRF_20_8_MHZ,
                                    tx_antenna_mask=0b1,
                                    rx_antenna_mask=0b1,
                                )
                            ],
                            sweeps_per_frame=16,
                            jitter_compensation=False,
                            inter_sweep_idle_state=a2.IdleState.ARMED,
                            inter_frame_idle_state=a2.IdleState.ARMED,
                            sweep_rate=None,
                            frame_rate=None,
                        ),
                    ],
                    update_rate=1.0,
                ),
                power.SensorConstants.ApsIdleState.APS_HF_WFI,
                power.SensorConstants.ApsActiveState.APS_HF,
            ).duration,
        ),
        (
            "frame_duration_conf2",
            power.frame_active(
                a2.SessionConfig(
                    sensor_configs=[
                        a2.SensorConfig(
                            subsweeps=[
                                a2.SubsweepConfig(
                                    start_point=100,
                                    num_points=100,
                                    step_length=1,
                                    hwaas_max=100,
                                    hwaas_min=10,
                                    hwaas_exponent=4,
                                    profile=a2.Profile.PROFILE_6,
                                    prf=a2.PRF.PRF_27_7_MHZ,
                                    tx_antenna_mask=0b111,
                                    rx_antenna_mask=0b1111,
                                )
                            ],
                            sweeps_per_frame=8,
                            jitter_compensation=False,
                            inter_sweep_idle_state=a2.IdleState.ARMED,
                            inter_frame_idle_state=a2.IdleState.ARMED,
                            sweep_rate=None,
                            frame_rate=None,
                        ),
                    ],
                    update_rate=1.0,
                ),
                power.SensorConstants.ApsIdleState.APS_HF_WFI,
                power.SensorConstants.ApsActiveState.APS_HF,
            ).duration,
        ),
        (
            "frame_duration_jitter_comp",
            power.frame_active(
                a2.SessionConfig(
                    sensor_configs=[
                        a2.SensorConfig(
                            subsweeps=[
                                a2.SubsweepConfig(
                                    start_point=100,
                                    num_points=100,
                                    step_length=1,
                                    hwaas_max=100,
                                    hwaas_min=10,
                                    hwaas_exponent=4,
                                    profile=a2.Profile.PROFILE_6,
                                    prf=a2.PRF.PRF_27_7_MHZ,
                                    tx_antenna_mask=0b111,
                                    rx_antenna_mask=0b1111,
                                )
                            ],
                            sweeps_per_frame=8,
                            jitter_compensation=True,
                            inter_sweep_idle_state=a2.IdleState.ARMED,
                            inter_frame_idle_state=a2.IdleState.ARMED,
                            sweep_rate=None,
                            frame_rate=None,
                        ),
                    ],
                    update_rate=1.0,
                ),
                power.SensorConstants.ApsIdleState.APS_HF_WFI,
                power.SensorConstants.ApsActiveState.APS_HF,
            ).duration,
        ),
    ],
)
def test_a2_frame_duration(
    a2_timing_limits: dict[str, t.Any],
    configuration: str,
    actual: float,
) -> None:
    unit_factor = 1e-6

    expected_current = (
        a2_timing_limits["radar_frame_duration_without_processing"]["gcc"][configuration]["target"]
        * unit_factor
    )
    absolute_tolerance = (
        a2_timing_limits["radar_frame_duration_without_processing"]["gcc"][configuration][
            "abs_tol"
        ]
        * unit_factor
    )

    assert actual == pytest.approx(expected_current, abs=absolute_tolerance)


@pytest.mark.parametrize(
    ("limit_name", "query", "actual"),
    [
        (
            "iq_processing_fixed_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().iq_processing_fixed,
        ),
        (
            "iq_processing_ms",
            'compiler == "gcc" and rss.jitter_compensation == True',
            power.SensorConstants.default().iq_processing_per_point,
        ),
        (
            "heatmap_capon_processing_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().capon_processing_per_param,
        ),
        (
            "heatmap_capon_update_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().capon_update_per_point,
        ),
        (
            "heatmap_coherent_processing_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().coherent_processing_per_param,
        ),
        (
            "heatmap_coherent_update_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().coherent_update_per_point,
        ),
        (
            "heatmap_conventional_processing_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().conventional_processing_per_param,
        ),
        (
            "heatmap_conventional_update_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().conventional_update_per_point,
        ),
        (
            "heatmap_robust_capon_processing_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().robust_capon_processing_per_param,
        ),
        (
            "heatmap_robust_capon_update_ms",
            'compiler == "gcc"',
            power.SensorConstants.default().robust_capon_update_per_point,
        ),
    ],
)
def test_a2_computation_time_limits(
    a2_computation_time_limits: dict[str, t.Any],
    limit_name: str,
    query: str,
    actual: float,
) -> None:
    unit_factor = 1e-3

    limits = a2_computation_time_limits[limit_name]["limits"]
    matching = [limit for limit in limits if query in limit["query"]]

    assert len(matching) == 1, f"{limit_name} has no single limit for {query}"

    gte = matching[0]["gte"] * unit_factor
    lte = matching[0]["lte"] * unit_factor

    assert gte <= actual <= lte


def _heatmap_duration(algorithm: power.algo.Algorithm, session_config: a2.SessionConfig) -> float:
    """Processing duration of the heatmap alone, without the Sparse IQ part"""
    aps_active_state = power.SensorConstants.ApsActiveState.APS_HF
    sensor = power.SensorConstants.default()

    total = algorithm.processing(session_config, aps_active_state, sensor)
    sparse_iq = power.algo.SparseIq().processing(session_config, aps_active_state, sensor)

    return total.duration - sparse_iq.duration


def _session_config(
    num_points: int = 16, tx_antenna_mask: int = 0b001, rx_antenna_mask: int = 0b0001
) -> a2.SessionConfig:
    return a2.SessionConfig(
        [
            a2.SensorConfig.single_subsweep(
                num_points=num_points,
                tx_antenna_mask=tx_antenna_mask,
                rx_antenna_mask=rx_antenna_mask,
                jitter_compensation=False,
            )
        ],
        update_rate=None,
    )


def _capon(num_az_angles: int = 25) -> power.algo.HeatmapCapon:
    return power.algo.HeatmapCapon(
        attrs.evolve(power.algo.HeatmapCaponConfig.default(), num_az_angles=num_az_angles)
    )


def _coherent() -> power.algo.HeatmapCoherent:
    return power.algo.HeatmapCoherent(power.algo.HeatmapCoherentConfig.default())


def test_heatmap_duration_is_linear_in_points() -> None:
    single = _heatmap_duration(_capon(), _session_config(num_points=16))
    double = _heatmap_duration(_capon(), _session_config(num_points=32))

    assert double == pytest.approx(2 * single)


def test_heatmap_duration_is_linear_in_the_angle_grid() -> None:
    single = _heatmap_duration(_capon(num_az_angles=25), _session_config())
    double = _heatmap_duration(_capon(num_az_angles=50), _session_config())

    # Only the per-param term grows with the grid, the per-point update does not
    update = 2 * single - double

    assert update > 0
    assert double - single == pytest.approx(single - update)


def test_covariance_heatmap_duration_grows_with_channels_to_the_power_of_1_5() -> None:
    """The processors share a covariance matrix per range point"""
    session_config = _session_config(rx_antenna_mask=0b1111)
    sensor = power.SensorConstants.default()
    subsweep = session_config.sensor_config.subsweep

    expected = (
        subsweep.num_points
        * _capon().heatmap_config.num_az_angles
        * subsweep.num_channels**1.5
        * sensor.capon_processing_per_param
        + subsweep.num_points * subsweep.num_channels * sensor.capon_update_per_point
    )

    assert _heatmap_duration(_capon(), session_config) == pytest.approx(expected)


def test_coherent_heatmap_processing_duration() -> None:
    """Follows the per-point costs measured by the RSS computation time test"""
    sensor = power.SensorConstants.default()
    heatmap_config = power.algo.HeatmapCoherentConfig.default()
    session_config = _session_config(tx_antenna_mask=0b111, rx_antenna_mask=0b1111)
    subsweep = session_config.sensor_config.subsweep
    num_channels = subsweep.num_channels

    expected = (
        subsweep.num_points
        * heatmap_config.num_az_angles
        * heatmap_config.num_el_angles
        * num_channels
        * sensor.coherent_processing_per_param
        + subsweep.num_points * num_channels * sensor.coherent_update_per_point
    )

    assert _heatmap_duration(_coherent(), session_config) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("tx_antenna_mask", "rx_antenna_mask", "num_channels"),
    [(0b001, 0b1111, 4), (0b111, 0b0001, 3), (0b111, 0b1111, 12)],
)
def test_coherent_heatmap_cost_is_linear_in_channels(
    tx_antenna_mask: int, rx_antenna_mask: int, num_channels: int
) -> None:
    """No covariance matrix is built, unlike the other three processors"""
    single = _heatmap_duration(_coherent(), _session_config())
    several = _heatmap_duration(
        _coherent(),
        _session_config(tx_antenna_mask=tx_antenna_mask, rx_antenna_mask=rx_antenna_mask),
    )

    assert several == pytest.approx(num_channels * single)
