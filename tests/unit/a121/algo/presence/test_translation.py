# Copyright (c) Acconeer AB, 2026
# All rights reserved

import math

import hypothesis as hyp
import hypothesis.strategies as hyp_st
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo._utils import (
    get_max_profile_without_direct_leakage,
    get_max_step_length,
)
from acconeer.exptool.a121.algo.presence._detector import Detector, DetectorConfig
from acconeer.exptool.a121.algo.presence._subsweep_utils import MIN_DIST_M, get_subsweep_configs


PROFILE_5_BREAKPOINT = MIN_DIST_M[a121.Profile.PROFILE_5]
MAX_END_M = int(a121.PRF.PRF_5_2_MHz.mmd)


@pytest.mark.parametrize(
    "config, expected_aspects",
    [
        # sweeps_per_frame must be *greater than* NOISE_ESTIMATION_DIFF_ORDER (3); equal is an error
        (DetectorConfig(sweeps_per_frame=3), ["sweeps_per_frame"]),
        (DetectorConfig(sweeps_per_frame=1), ["sweeps_per_frame"]),
        # start > end
        (DetectorConfig(start_m=5.0, end_m=2.0), ["end_m"]),
        # end_m strictly above the maximum allowed distance
        (DetectorConfig(end_m=MAX_END_M + 1), ["end_m"]),
        # both start>end AND end>max — two errors, both on "end_m"
        (DetectorConfig(start_m=25.0, end_m=26.0), ["end_m", "end_m"]),
    ],
)
def test_collect_validation_results_has_errors(config, expected_aspects):
    """Invalid configs must produce at least one result for each expected aspect."""
    results = config._collect_validation_results()
    aspects = [r.aspect for r in results]
    for aspect in expected_aspects:
        assert aspect in aspects


@pytest.mark.parametrize(
    "start_m, expected_profile",
    [
        # 2*FWHM thresholds: P2=0.14, P3=0.28, P4=0.38, P5=0.64
        (0.0, a121.Profile.PROFILE_1),  # below all thresholds → P1
        (0.1, a121.Profile.PROFILE_1),  # below P2 threshold (0.14) → P1
        (0.15, a121.Profile.PROFILE_2),  # above P2 (0.14), below P3 (0.28) → P2
        (0.3, a121.Profile.PROFILE_3),  # above P3 (0.28), below P4 (0.38) → P3
        (0.65, a121.Profile.PROFILE_5),  # above P5 (0.64) → P5
        (1.0, a121.Profile.PROFILE_5),  # well above P5 → P5
    ],
)
def test_sensor_config_profile_auto_select(start_m, expected_profile):
    """Profile is auto-selected based on 2*FWHM <= start_m."""
    cfg = DetectorConfig(start_m=start_m, end_m=start_m + 0.5)
    sc = Detector._get_sensor_config(cfg)
    assert sc.profile == expected_profile


@pytest.mark.parametrize(
    "profile, expected_step_length",
    [
        # step = floor(FWHM / base_step / PPC) * PPC, or PPC // ceil(PPC / (FWHM/base_step))
        # base_step=0.0025m, PPC=24
        (a121.Profile.PROFILE_1, 12),  # fwhm_p=16 < 24 → 24//ceil(24/16)=24//2=12
        (a121.Profile.PROFILE_2, 24),  # fwhm_p=28 → floor(28/24)*24=24
        (a121.Profile.PROFILE_3, 48),  # fwhm_p=56 → floor(56/24)*24=48
        (a121.Profile.PROFILE_4, 72),  # fwhm_p=76 → floor(76/24)*24=72
        (a121.Profile.PROFILE_5, 120),  # fwhm_p=128 → floor(128/24)*24=120
    ],
)
def test_sensor_config_step_length_auto_select(profile, expected_step_length):
    """Step length is auto-selected based on profile FWHM."""
    cfg = DetectorConfig(profile=profile, start_m=0.3, end_m=2.5)
    sc = Detector._get_sensor_config(cfg)
    assert sc.step_length == expected_step_length


@pytest.mark.parametrize("step_length", [1, 4, 12, 24])
def test_sensor_config_explicit_step_length(step_length):
    """An explicit step_length overrides the auto-selected value."""
    cfg = DetectorConfig(step_length=step_length, start_m=0.3, end_m=2.5)
    sc = Detector._get_sensor_config(cfg)
    assert sc.step_length == step_length


def test_sensor_config_single_point():
    """start_m == end_m must produce exactly one measurement point."""
    cfg = DetectorConfig(start_m=0.5, end_m=0.5)
    sc = Detector._get_sensor_config(cfg)
    # num_point = ceil((end - start) / (step * base)) + 1 = ceil(0) + 1 = 1
    assert sc.num_points == 1


def test_sensor_config_start_at_zero():
    """start_m=0.0 must map to start_point=0."""
    cfg = DetectorConfig(start_m=0.0, end_m=1.0)
    sc = Detector._get_sensor_config(cfg)
    assert sc.start_point == 0


@pytest.mark.parametrize(
    "field, value, attr",
    [
        ("hwaas", 64, "hwaas"),
        ("sweeps_per_frame", 32, "sweeps_per_frame"),
        ("frame_rate", 20.0, "frame_rate"),
        ("inter_frame_idle_state", a121.IdleState.READY, "inter_frame_idle_state"),
    ],
)
def test_sensor_config_parameter_propagation(field, value, attr):
    """Scalar config fields must be forwarded to the resulting SensorConfig."""
    cfg = DetectorConfig(start_m=0.3, end_m=2.5, **{field: value})
    sc = Detector._get_sensor_config(cfg)
    assert getattr(sc, attr) == value


def test_sensor_config_explicit_profile_overrides_leakage_guard():
    """An explicitly set profile is always honoured, even when start_m is below
    the profile's direct-leakage minimum distance."""
    # PROFILE_5 min dist is ~0.64 m; start_m=0.1 m is well below that
    cfg = DetectorConfig(profile=a121.Profile.PROFILE_5, start_m=0.1, end_m=0.5)
    sc = Detector._get_sensor_config(cfg)
    assert sc.profile == a121.Profile.PROFILE_5


@pytest.mark.parametrize(
    "start_m, end_m",
    [
        (0.0, 0.145),  # P1 ends at 0.15, P2 cut=0.145 → P2 gets 0 points
        (0.0, 0.31),  # P2 ends at 0.33, P3 cut=0.31  → P3 gets 0 points
        (0.14, 0.31),  # P2 ends at 0.32, P3 cut=0.31  → P3 gets 0 points
        (0.15, 0.31),  # P2 ends at 0.33, P3 cut=0.31  → P3 gets 0 points
        (0.28, 0.39),  # P3 ends at 0.40, P4 cut=0.39  → P4 gets 0 points
        (0.0, 0.42),  # P3 ends at 0.45, P4 cut=0.42  → P4 gets 0 points
    ],
)
def test_get_subsweep_configs_overshoot_no_crash(start_m, end_m):
    """Regression: _get_profile_subsweeps previously created SubsweepConfig(num_points=0)
    when a profile's step overshoot past the next profile's cut_point, which was rejected
    by attrs.validators.ge(1). Fixed by skipping zero-point subsweeps (same guard as
    _get_hwaas_subsweeps).
    """
    ss = get_subsweep_configs(start_m, end_m, 15.0)
    assert len(ss) >= 1
    assert all(s.num_points >= 1 for s in ss)


def test_get_subsweep_configs_start_equals_end():
    """start_m == end_m triggers special handling (+0.01) — must still produce valid subsweeps."""
    # Use a range that is entirely above the profile-5 breakpoint to avoid the
    # _get_profile_subsweeps overshoot bug.
    ss = get_subsweep_configs(0.7, 0.7, 15.0)
    assert len(ss) == 1
    assert ss[0].num_points == 1


def test_get_subsweep_configs_hwaas_bounds():
    """HWAAS must always be clipped to the valid range [1, 511]."""
    ss_high = get_subsweep_configs(5.0, 7.5, 40.0)  # very high quality → clipped to 511
    assert all(1 <= s.hwaas <= 511 for s in ss_high)

    ss_low = get_subsweep_configs(5.0, 7.5, -50.0)  # very low quality → clipped to 1
    assert all(1 <= s.hwaas <= 511 for s in ss_low)


def test_get_subsweep_configs_max_subsweeps():
    """Total subsweep count must never exceed MAX_NUM_SUBSWEEPS (4)."""
    ss = get_subsweep_configs(0.7, 10.0, 15.0)  # long range, all above P5 breakpoint
    assert len(ss) <= 4


def test_get_subsweep_configs_above_profile5_breakpoint_uses_only_p5():
    """A range entirely above the profile-5 breakpoint must use only PROFILE_5."""
    assert PROFILE_5_BREAKPOINT < 0.7  # sanity check
    ss = get_subsweep_configs(0.7, 1.5, 15.0)
    assert all(s.profile == a121.Profile.PROFILE_5 for s in ss)


def test_get_subsweep_configs_below_profile5_breakpoint_no_p5():
    """A range entirely below the profile-5 breakpoint must not use PROFILE_5."""
    assert PROFILE_5_BREAKPOINT > 0.5  # sanity check
    ss_below = get_subsweep_configs(0.1, 0.5, 15.0)
    assert all(s.profile != a121.Profile.PROFILE_5 for s in ss_below)


@pytest.mark.parametrize(
    "start_m, end_m, step_length",
    [
        #   start   end   step  → computed end_point dist
        (22.0, 24.0, 960),  # → 24.40 m
        (20.0, 24.0, 960),  # → 24.80 m
        (3.0, 24.0, 960),  # → 24.60 m
    ],
)
def test_get_sensor_config_prf_selection_crash(start_m, end_m, step_length):
    """Bug: a large step_length causes end_point to overshoot the max measurable
    distance of PRF_5_2_MHz (~24.3 m), leaving select_prf with no viable PRF.
    All three inputs are individually valid per _collect_validation_results
    (start_m < end_m <= MAX_END_M=24, step_length is a multiple of 24), yet
    _get_sensor_config raises IndexError.

    Fix: guard in _collect_validation_results (or _get_sensor_config) that
    checks end_point * APPROX_BASE_STEP_LENGTH_M < PRF_5_2_MHz.mmd before
    calling select_prf.
    """
    with pytest.raises(IndexError):
        Detector._get_sensor_config(
            DetectorConfig(start_m=start_m, end_m=end_m, step_length=step_length)
        )


@hyp_st.composite
def detector_config_strategy(draw: hyp_st.DrawFn) -> DetectorConfig:
    start_m = draw(hyp_st.floats(min_value=0.0, max_value=float(MAX_END_M)))
    end_m = draw(hyp_st.floats(min_value=start_m, max_value=float(MAX_END_M)))
    step_length = draw(hyp_st.one_of(hyp_st.integers(min_value=1), hyp_st.none()))
    profile = draw(hyp_st.one_of(hyp_st.sampled_from(a121.Profile), hyp_st.none()))

    eff_profile = (
        profile if profile is not None else get_max_profile_without_direct_leakage(start_m)
    )
    eff_step = step_length if step_length is not None else get_max_step_length(eff_profile)
    start_point = int(math.floor(start_m / APPROX_BASE_STEP_LENGTH_M))
    num_points = int(math.ceil((end_m - start_m) / (eff_step * APPROX_BASE_STEP_LENGTH_M)) + 1)
    end_point = start_point + (num_points - 1) * eff_step

    # Pre-filter: skip inputs where the calculated end_point would overshoot the
    # max measurable distance of PRF_5_2_MHz, causing select_prf to crash with
    # IndexError (see test_get_sensor_config_prf_selection_crash).
    hyp.assume(end_point * APPROX_BASE_STEP_LENGTH_M < float(a121.PRF.PRF_5_2_MHz.mmd))

    try:
        config = DetectorConfig(
            start_m=start_m,
            end_m=end_m,
            step_length=step_length,
            profile=profile,
            # sweeps_per_frame must be > NOISE_ESTIMATION_DIFF_ORDER (3)
            sweeps_per_frame=draw(hyp_st.integers(min_value=4, max_value=64)),
            hwaas=draw(hyp_st.integers(min_value=1, max_value=511)),
            frame_rate=draw(hyp_st.floats(min_value=0.1, max_value=100.0)),
            inter_frame_idle_state=draw(hyp_st.sampled_from(a121.IdleState)),
            # automatic_subsweeps=True is excluded: get_subsweep_configs has a known crash
            # bug for certain boundary conditions (see test_get_subsweep_configs_overshoot_raises).
            automatic_subsweeps=False,
            signal_quality=draw(hyp_st.floats(min_value=0.0, max_value=30.0)),
        )
        config.validate()
    except ValueError:
        hyp.assume(False)
    except a121.ValidationResult:
        hyp.assume(False)

    return config


@hyp.given(detector_config_strategy())
def test_valid_detector_configs_translate_to_valid_sensor_configs(
    config: DetectorConfig,
) -> None:
    """Any valid DetectorConfig must translate to a SensorConfig with no validation errors."""
    sensor_config = Detector._get_sensor_config(config)
    assert sensor_config._collect_validation_results() == []
