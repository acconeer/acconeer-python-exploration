# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
from __future__ import annotations

import typing as t

import hypothesis as hyp
import hypothesis.strategies as hyp_st
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import distance, select_prf


def test_m_to_points() -> None:
    assert distance._translation._m_to_point(start_m=0.5, distance_m=0.5, step_length=4) == 200
    assert distance._translation._m_to_point(start_m=0.5, distance_m=1.0, step_length=4) == 400
    assert distance._translation._m_to_point(start_m=0.5, distance_m=1.5, step_length=4) == 600


def test_select_prf() -> None:
    breakpoint = 600
    profile = a121.Profile.PROFILE_3

    actual_PRF = select_prf(breakpoint=breakpoint, profile=profile)

    assert actual_PRF == a121.PRF.PRF_15_6_MHz


def test_limit_step_length() -> None:
    profile = a121.Profile.PROFILE_3
    user_limit = 2

    actual_step_length = distance._translation._limit_step_length(
        profile=profile, user_limit=user_limit
    )
    assert actual_step_length == 2

    actual_step_length_no_user_limit = distance._translation._limit_step_length(
        profile=profile, user_limit=None
    )
    assert actual_step_length_no_user_limit == 12


@pytest.mark.parametrize("profile", [a121.Profile.PROFILE_1, a121.Profile.PROFILE_3])
@pytest.mark.parametrize("step_length", [1, 12])
@pytest.mark.parametrize("reflector_shape_exponent", [2.0, 4.0])
def test_hwaas_saturation_m_round_trips_through_calc_hwaas(
    profile: a121.Profile, step_length: int, reflector_shape_exponent: float
) -> None:
    """_calc_hwaas_saturation_m is the analytic inverse of _calc_hwaas - lock them together."""
    signal_quality = 15.0

    saturation_m = distance._translation._calc_hwaas_saturation_m(
        profile, step_length, signal_quality, reflector_shape_exponent
    )

    assert (
        distance._translation._calc_hwaas(
            profile, step_length, saturation_m, signal_quality, reflector_shape_exponent
        )
        == distance._translation._MAX_HWAAS
    )


def test_max_profile_breakpoints_anchor_to_hwaas_saturation_when_inside_range() -> None:
    """Saturation point inside range: spacing anchors to it, last breakpoint pulled to end_m."""
    profile = a121.Profile.PROFILE_3
    step_length = 12
    signal_quality = 15.0
    reflector_shape_exponent = 4.0
    start_m = 0.0
    end_m = 10.0
    num_breakpoints = 5

    saturation_m = distance._translation._calc_hwaas_saturation_m(
        profile, step_length, signal_quality, reflector_shape_exponent
    )
    assert start_m < saturation_m <= end_m  # sanity check: this exercises the anchor branch

    breakpoints = distance._translation._calc_max_profile_breakpoints_m(
        start_m,
        end_m,
        num_breakpoints,
        profile,
        step_length,
        signal_quality,
        reflector_shape_exponent,
    )

    # Golden values recorded from the current implementation. Changing
    # distance._translation._BREAKPOINT_DENSITY_EXPONENT will break this test.
    expected = [0.0, 2.5177895170097013, 3.9508352337939048, 5.142191386643525, 10.0]

    assert breakpoints == pytest.approx(expected)
    assert breakpoints[0] == start_m
    assert breakpoints[-1] == end_m


def test_max_profile_breakpoints_fall_back_to_full_range_when_saturation_outside_range() -> None:
    """Saturation point outside range: spacing falls back to the full [start_m, end_m] span."""
    profile = a121.Profile.PROFILE_3
    step_length = 12
    signal_quality = 15.0
    reflector_shape_exponent = 4.0
    start_m = 0.0
    end_m = 5.0  # shorter than the ~6.2 m saturation distance computed below
    num_breakpoints = 5

    saturation_m = distance._translation._calc_hwaas_saturation_m(
        profile, step_length, signal_quality, reflector_shape_exponent
    )
    assert not (start_m < saturation_m <= end_m)  # sanity check: this exercises the fallback

    breakpoints = distance._translation._calc_max_profile_breakpoints_m(
        start_m,
        end_m,
        num_breakpoints,
        profile,
        step_length,
        signal_quality,
        reflector_shape_exponent,
    )

    # Golden values recorded from the current implementation. Changing
    # distance._translation._BREAKPOINT_DENSITY_EXPONENT will break this test.
    expected = [0.0, 2.0306309908905886, 3.1864015682981557, 4.147246273076272, 5.0]

    assert breakpoints == pytest.approx(expected)


def test_should_be_able_to_set_start_m_equals_end_m() -> None:
    config = distance.DetectorConfig(start_m=0.8, end_m=0.8)
    client: t.Any = None
    try:
        distance.Detector(client=client, sensor_ids=[1], detector_config=config, context=None)
    except Exception:
        pytest.fail("Should not raise Exception")


@hyp_st.composite
def detector_config_strategy(draw: hyp_st.DrawFn) -> distance.DetectorConfig:
    start_m = draw(
        hyp_st.floats(
            min_value=distance.Detector.MIN_DIST_M,
            max_value=distance.Detector.MAX_DIST_M,
        )
    )
    end_m = draw(hyp_st.floats(min_value=start_m, max_value=distance.Detector.MAX_DIST_M))
    max_step_length = draw(
        hyp_st.one_of(
            # valid step length in [1, 23]
            hyp_st.integers(min_value=1, max_value=23).filter(lambda n: 24 % n == 0),
            # valid step length in [24, 960]
            hyp_st.integers(min_value=1, max_value=40).map(lambda n: n * 24),
            hyp_st.none(),
        )
    )
    max_profile = draw(hyp_st.sampled_from(a121.Profile))

    config = distance.DetectorConfig(
        start_m=start_m,
        end_m=end_m,
        max_step_length=max_step_length,
        max_profile=max_profile,
        close_range_leakage_cancellation=draw(hyp_st.booleans()),
        signal_quality=draw(hyp_st.floats(min_value=0.0, max_value=30.0)),
        threshold_method=draw(hyp_st.sampled_from(distance.ThresholdMethod)),
        peaksorting_method=draw(hyp_st.sampled_from(distance.PeakSortingMethod)),
        reflector_shape=draw(hyp_st.sampled_from(distance.ReflectorShape)),
        num_frames_in_recorded_threshold=draw(hyp_st.integers(min_value=0, max_value=300)),
        fixed_threshold_value=draw(hyp_st.floats()),
        threshold_sensitivity=draw(hyp_st.floats()),
        update_rate=draw(
            hyp_st.one_of(
                hyp_st.floats(min_value=0.000001),
                hyp_st.none(),
            ),
        ),
    )

    try:
        config.validate()
    except a121.ValidationResult:
        # discards invalid distance.DetectorConfigs
        hyp.assume(False)

    return config


@hyp.given(detector_config_strategy())
def test_valid_detector_configs_translates_to_valid_session_configs(
    detector_config: distance.DetectorConfig,
) -> None:
    session_config = distance.detector_config_to_session_config(
        config=detector_config, sensor_ids=[1]
    )

    session_config.validate()
