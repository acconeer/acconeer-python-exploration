# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import (
    DetectorConfig,
    PeakSortingMethod,
    ReflectorShape,
    ThresholdMethod,
    carry_over_signal_quality,
    detector_config_to_session_config,
)


def _subsweeps(session_config):
    return [
        subsweep
        for group in session_config.groups
        for sensor_config in group.values()
        for subsweep in sensor_config.subsweeps
    ]


@pytest.mark.parametrize(
    "detector_config,expected_session_config",
    [
        pytest.param(
            DetectorConfig(),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=48,
                                    num_points=87,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=68,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=264,
                                    num_points=26,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=888,
                                    num_points=4,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=7,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=984,
                                    num_points=2,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=8,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1032,
                                    num_points=2,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=10,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1080,
                                    num_points=3,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=13,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1152,
                                    num_points=18,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=15,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.05,
                end_m=6.0,
                max_profile=a121.Profile.PROFILE_3,
                signal_quality=20.0,
                num_frames_in_recorded_threshold=100,
                threshold_sensitivity=0.0,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=-32,
                                    num_points=107,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=67,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=9,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=924,
                                    num_points=27,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=29,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1248,
                                    num_points=23,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=65,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=1524,
                                    num_points=20,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=117,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1764,
                                    num_points=19,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=190,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1992,
                                    num_points=17,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=281,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=2196,
                                    num_points=31,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=400,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_13_0_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.2,
                end_m=0.860397,
                max_profile=a121.Profile.PROFILE_3,
                signal_quality=20.0,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=28,
                                    num_points=92,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=32,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=1,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.2,
                end_m=0.890396,
                max_profile=a121.Profile.PROFILE_3,
                signal_quality=20.0,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=28,
                                    num_points=92,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=33,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=1,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(start_m=0.05, end_m=0.1, close_range_leakage_cancellation=True),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=0,
                                    num_points=1,
                                    step_length=1,
                                    profile=a121.Profile.PROFILE_4,
                                    hwaas=2,
                                    receiver_gain=15,
                                    enable_tx=True,
                                    enable_loopback=True,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=4,
                                    num_points=13,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=5,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=10,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.1,
                end_m=3.0,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=-12,
                                    num_points=102,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=68,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=264,
                                    num_points=26,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=888,
                                    num_points=4,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=7,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=984,
                                    num_points=2,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=8,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1032,
                                    num_points=2,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=10,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1080,
                                    num_points=3,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=13,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1152,
                                    num_points=18,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=15,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.1,
                end_m=3.0,
                close_range_leakage_cancellation=True,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=0,
                                    num_points=1,
                                    step_length=1,
                                    profile=a121.Profile.PROFILE_4,
                                    hwaas=2,
                                    receiver_gain=15,
                                    enable_tx=True,
                                    enable_loopback=True,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=24,
                                    num_points=23,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=5,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=10,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=16,
                                    num_points=95,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=68,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=264,
                                    num_points=26,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=888,
                                    num_points=4,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=7,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=984,
                                    num_points=2,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=8,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1032,
                                    num_points=2,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=10,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1080,
                                    num_points=3,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=13,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1152,
                                    num_points=18,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=15,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.02,
                end_m=0.5,
                max_step_length=1,
                max_profile=a121.Profile.PROFILE_1,
                close_range_leakage_cancellation=False,
                signal_quality=20.0,
                threshold_method=ThresholdMethod.FIXED_STRENGTH,
                peaksorting_method=PeakSortingMethod.STRONGEST,
                reflector_shape=ReflectorShape.PLANAR,
                num_frames_in_recorded_threshold=50,
                threshold_sensitivity=0.5,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=-8,
                                    num_points=224,
                                    step_length=1,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=1,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_19_5_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.0,
                end_m=0.2,
                max_step_length=1,
                max_profile=a121.Profile.PROFILE_1,
                close_range_leakage_cancellation=True,
                signal_quality=15.0,
                threshold_method=ThresholdMethod.CFAR,
                peaksorting_method=PeakSortingMethod.CLOSEST,
                reflector_shape=ReflectorShape.GENERIC,
                num_frames_in_recorded_threshold=30,
                threshold_sensitivity=0.5,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=0,
                                    num_points=1,
                                    step_length=1,
                                    profile=a121.Profile.PROFILE_4,
                                    hwaas=1,
                                    receiver_gain=15,
                                    enable_tx=True,
                                    enable_loopback=True,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=-16,
                                    num_points=112,
                                    step_length=1,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=1,
                                    receiver_gain=5,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=10,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(start_m=0.1, end_m=10.0, close_range_leakage_cancellation=True),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=0,
                                    num_points=1,
                                    step_length=1,
                                    profile=a121.Profile.PROFILE_4,
                                    hwaas=2,
                                    receiver_gain=15,
                                    enable_tx=True,
                                    enable_loopback=True,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=24,
                                    num_points=23,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=5,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=10,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=16,
                                    num_points=95,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=120,
                                    num_points=68,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=264,
                                    num_points=48,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=30,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1416,
                                    num_points=16,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=78,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=1800,
                                    num_points=13,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=147,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=2112,
                                    num_points=11,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=235,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=2376,
                                    num_points=11,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=359,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=2640,
                                    num_points=72,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=511,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_8_7_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.05,
                end_m=0.10,
                close_range_leakage_cancellation=False,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=-32,
                                    num_points=31,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_19_5_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=1.93,
                end_m=3.0,
                max_profile=a121.Profile.PROFILE_5,
                max_step_length=None,
                threshold_method=ThresholdMethod.CFAR,
                close_range_leakage_cancellation=False,
                signal_quality=25.4,
                reflector_shape=ReflectorShape.PLANAR,
                num_frames_in_recorded_threshold=50,
                fixed_threshold_value=100.0,
                fixed_strength_threshold_value=5.0,
                threshold_sensitivity=0.94,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=384,
                                    num_points=25,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=3,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=984,
                                    num_points=5,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=4,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1104,
                                    num_points=20,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.86,
                end_m=3.0,
                max_profile=a121.Profile.PROFILE_5,
                max_step_length=None,
                threshold_method=ThresholdMethod.CFAR,
                close_range_leakage_cancellation=False,
                signal_quality=25.4,
                reflector_shape=ReflectorShape.PLANAR,
                num_frames_in_recorded_threshold=50,
                fixed_threshold_value=100.0,
                fixed_strength_threshold_value=5.0,
                threshold_sensitivity=0.94,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=168,
                                    num_points=64,
                                    step_length=12,
                                    profile=a121.Profile.PROFILE_3,
                                    hwaas=4,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=264,
                                    num_points=31,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=3,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1008,
                                    num_points=4,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=4,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                                a121.SubsweepConfig(
                                    start_point=1104,
                                    num_points=20,
                                    step_length=24,
                                    profile=a121.Profile.PROFILE_5,
                                    hwaas=5,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_15_6_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.8,
                end_m=0.8,
                close_range_leakage_cancellation=False,
            ),
            a121.SessionConfig(
                [
                    {
                        1: a121.SensorConfig(
                            subsweeps=[
                                a121.SubsweepConfig(
                                    start_point=268,
                                    num_points=27,
                                    step_length=4,
                                    profile=a121.Profile.PROFILE_1,
                                    hwaas=2,
                                    receiver_gain=10,
                                    enable_tx=True,
                                    enable_loopback=False,
                                    phase_enhancement=True,
                                    iq_imbalance_compensation=True,
                                    prf=a121.PRF.PRF_19_5_MHz,
                                ),
                            ],
                            sweeps_per_frame=1,
                            sweep_rate=None,
                            frame_rate=None,
                            continuous_sweep_mode=False,
                            double_buffering=False,
                            inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
                            inter_sweep_idle_state=a121.IdleState.READY,
                        ),
                    },
                ],
                extended=True,
                update_rate=50.0,
            ),
        ),
    ],
)
def test_session_translation(detector_config, expected_session_config):
    session_config = detector_config_to_session_config(detector_config, [1])

    # to_dict() gives a nice diff if assertion fail
    assert session_config.to_dict() == expected_session_config.to_dict()

    # Make sure to compare the actual config object equality
    assert session_config == expected_session_config


@pytest.mark.parametrize(
    ("max_profile", "max_step_length", "expected_offset"),
    [
        (a121.Profile.PROFILE_5, None, 5.8),
        (a121.Profile.PROFILE_3, 2, 11.6),
        (a121.Profile.PROFILE_4, 6, 8.7),
        (a121.Profile.PROFILE_1, None, 5.2),
    ],
)
def test_carry_over_signal_quality_offset(max_profile, max_step_length, expected_offset):
    config = DetectorConfig(
        max_profile=max_profile, max_step_length=max_step_length, signal_quality=20.0
    )

    carried = carry_over_signal_quality(config)

    assert carried.signal_quality == pytest.approx(20.0 + expected_offset, abs=0.05)
    assert config.signal_quality == 20.0


def test_signal_quality_offset_follows_the_profile_reaching_furthest():
    # A range this short ends before max profile is used and measures with profile 1
    # only, at HWAAS 21 before the gain fix, as door open detection does.
    short_range = DetectorConfig(
        start_m=0.1,
        end_m=0.35,
        signal_quality=25.0,
        threshold_sensitivity=0.5,
        reflector_shape=ReflectorShape.PLANAR,
    )

    converted = carry_over_signal_quality(short_range)

    assert converted.signal_quality == pytest.approx(25.0 + 5.2, abs=0.05)
    session_config = detector_config_to_session_config(converted, [1])
    assert [(s.profile, s.hwaas) for s in _subsweeps(session_config)] == [
        (a121.Profile.PROFILE_1, 21)
    ]


def test_carry_over_signal_quality_reproduces_the_hwaas_from_before_the_gain_fix():
    # what the old default configuration measured while only a tenth of the gain was used
    old_default = DetectorConfig(signal_quality=15.0)
    expected_hwaas = [2, 5, 5, 7, 8, 10, 13, 15]

    session_config = detector_config_to_session_config(carry_over_signal_quality(old_default), [1])

    assert [subsweep.hwaas for subsweep in _subsweeps(session_config)] == expected_hwaas


def test_transition_keeps_its_subsweep_at_equal_hwaas():
    # A transition carries a profile and a step length of its own, so it stays a
    # subsweep of its own even where it lands on the HWAAS of its neighbour.
    subsweeps = _subsweeps(detector_config_to_session_config(DetectorConfig(), [1]))

    assert len(subsweeps) == 8
    assert subsweeps[1].profile == a121.Profile.PROFILE_3
    assert subsweeps[2].profile == a121.Profile.PROFILE_5
    assert subsweeps[1].hwaas == subsweeps[2].hwaas
    assert subsweeps[1].step_length != subsweeps[2].step_length


def test_merged_subsweep_covers_the_whole_span():
    config = DetectorConfig(
        start_m=0.05,
        end_m=0.15,
        max_step_length=1,
        max_profile=a121.Profile.PROFILE_1,
        close_range_leakage_cancellation=False,
        signal_quality=20.0,
        threshold_method=ThresholdMethod.FIXED,
    )

    session_config = detector_config_to_session_config(config, [1])
    (subsweep,) = _subsweeps(session_config)

    # A range this short measures at one HWAAS throughout, so one subsweep spans it.
    assert len(session_config.groups) == 1
    assert (subsweep.start_point, subsweep.num_points, subsweep.step_length) == (4, 72, 1)
    assert subsweep.profile == a121.Profile.PROFILE_1
    assert subsweep.hwaas == 1


def test_merging_frees_the_second_group():
    config = DetectorConfig(
        start_m=0.1,
        end_m=0.8,
        max_profile=a121.Profile.PROFILE_3,
        signal_quality=15.0,
        threshold_method=ThresholdMethod.FIXED,
    )

    session_config = detector_config_to_session_config(config, [1])

    # Unmerged, this range takes seven subsweeps and so a second sensor config.
    assert len(session_config.groups) == 1
    assert [
        (s.start_point, s.num_points, s.step_length, s.profile, s.hwaas)
        for s in _subsweeps(session_config)
    ] == [
        (24, 54, 4, a121.Profile.PROFILE_1, 1),
        (120, 20, 12, a121.Profile.PROFILE_3, 1),
    ]


def test_merging_keeps_a_boundary_the_sensor_buffer_needs():
    config = DetectorConfig(
        start_m=0.05,
        end_m=10.9,
        max_step_length=1,
        max_profile=a121.Profile.PROFILE_5,
        signal_quality=10.0,
    )

    session_config = detector_config_to_session_config(config, [1])

    # Merging the two HWAAS 1 subsweeps would pull the HWAAS 3 one into the first
    # sensor config, taking it to 4117 points against the 4095 it holds.
    session_config.validate()
    assert [(s.start_point, s.num_points, s.hwaas) for s in _subsweeps(session_config)] == [
        (-32, 434, 1),
        (112, 870, 1),
        (256, 1655, 1),
        (1911, 632, 1),
        (2543, 526, 3),
        (3069, 466, 5),
        (3535, 427, 8),
        (3962, 814, 11),
    ]


@pytest.mark.parametrize(
    ("start_m", "end_m", "max_profile", "signal_quality"),
    [
        (0.05, 6.6, a121.Profile.PROFILE_5, 10.0),
        (0.25, 11.3, a121.Profile.PROFILE_5, 10.0),
        (0.05, 10.3, a121.Profile.PROFILE_4, 5.0),
    ],
)
def test_merging_never_overfills_a_sensor_config(start_m, end_m, max_profile, signal_quality):
    config = DetectorConfig(
        start_m=start_m,
        end_m=end_m,
        max_step_length=1,
        max_profile=max_profile,
        signal_quality=signal_quality,
    )

    detector_config_to_session_config(config, [1]).validate()
