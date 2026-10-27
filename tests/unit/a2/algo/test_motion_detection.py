# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for MotionDetectionConfig and the radii helpers."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import ValidationError
from acconeer.exptool.a2.algo._detection_geometry import DetectionVolume, SensorInstallation
from acconeer.exptool.a2.algo._utils import (
    BASE_STEP_LENGTH_M,
    CONVENTIONAL_AZ_FWHM_DEG,
    ENVELOPE_LENGTH_M,
)
from acconeer.exptool.a2.algo.motion_detection.config import (
    _MAX_PEAK_FINDING_AZ_RADIUS_BINS,
    _MAX_PEAK_FINDING_DIST_RADIUS_BINS,
    _N_EL_INTERPOLATION,
    BeamformingMethod,
    MotionDetectionConfig,
    _cells_from_deg,
    _cells_from_length,
    _compute_cfar_radii,
    _compute_peak_finding_radii,
)
from acconeer.exptool.a2.algo.nodes._cfar_subnodes import CFARAggregateMethod
from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import InterpolationMethod2D


_DEFAULT_INSTALLATION = SensorInstallation(mount_height_m=0.5)
_DEFAULT_VOLUME = DetectionVolume(x_bounds_m=(-1.0, 1.0), y_bounds_m=(0.1, 1.0))


# -- _cells_from_deg ----------------------------------------------------------


def test_cells_from_deg_single_cell_axis_returns_zero():
    assert _cells_from_deg(span_deg=0.0, num_angles=1, radius_deg=8.0) == 0


def test_cells_from_deg_multi_cell_axis():
    assert _cells_from_deg(span_deg=120.0, num_angles=61, radius_deg=4.0) == 2


def test_cells_from_deg_nonzero_radius_floored_at_one():
    assert _cells_from_deg(span_deg=120.0, num_angles=61, radius_deg=0.1) == 1


def test_cells_from_deg_zero_radius_yields_zero():
    assert _cells_from_deg(span_deg=120.0, num_angles=61, radius_deg=0.0) == 0


# -- _cells_from_length ------------------------------------------------------


def test_cells_from_length_rounds_to_nearest_cell():
    step_length_m = 0.05
    length = ENVELOPE_LENGTH_M[a2.Profile.PROFILE_3]
    expected = round(1.5 * length / step_length_m)
    assert _cells_from_length(length, step_length_m, factor=1.5) == expected


# -- _num_from_resolution ----------------------------------------------------


def test_num_from_resolution_exact_divisor():
    # 120 / 2 = 60 intervals -> 61 angles, no rounding
    assert MotionDetectionConfig._num_from_resolution((-60.0, 60.0), 2.0) == 61


def test_num_from_resolution_rounds_to_nearest():
    # 120 / 7 ≈ 17.14 -> 17 intervals -> 18 angles
    assert MotionDetectionConfig._num_from_resolution((-60.0, 60.0), 7.0) == 18


def test_num_from_resolution_off_grid_rounds_down():
    # 120 / 2.03 ≈ 59.11 -> 59 intervals -> 60 angles (matches old 60-bin default)
    assert MotionDetectionConfig._num_from_resolution((-60.0, 60.0), 2.03) == 60


def test_num_from_resolution_zero_span_short_circuits():
    assert MotionDetectionConfig._num_from_resolution((0.0, 0.0), 5.0) == 1


def test_num_from_resolution_resolution_larger_than_span_clamps_to_two():
    # round(120 / 200) = 1 (since round() goes to nearest), so 2 angles.
    assert MotionDetectionConfig._num_from_resolution((-60.0, 60.0), 200.0) == 2
    # Without the max(1, ...) clamp this would be 1 angle for a non-zero range.
    assert MotionDetectionConfig._num_from_resolution((-60.0, 60.0), 1000.0) == 2


def test_num_el_angles_returns_one_when_resolution_is_none():
    config = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212, el_grid_resolution_deg=None
    )
    assert config.num_el_angles(_DEFAULT_VOLUME) == 1


def test_el_angles_ignore_range_when_resolution_is_none():
    config = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        el_angle_range=(-30.0, 30.0),
        el_grid_resolution_deg=None,
    )
    np.testing.assert_array_equal(config.el_angles(_DEFAULT_VOLUME), np.array([0.0]))


# -- _compute_cfar_radii -----------------------------------------------------


def test_compute_cfar_radii_single_az_yields_zero_az_radii():
    (_, n_g_a), (_, n_r_a) = _compute_cfar_radii(
        az_span=0.0,
        num_az_angles=1,
        profile=a2.Profile.PROFILE_3,
        step_length_m=0.05,
        num_points=41,
        az_guard_fwhm_factor=0.78,
        dist_guard_envelope_len_factor=1.0,
        az_reference_fwhm_factor=0.78,
        dist_reference_envelope_len_factor=0.5,
    )
    assert n_g_a == 0
    assert n_r_a == 0


def test_compute_cfar_radii_clamps_to_half_grid():
    # 3-cell grid -> max permissible radius is (3-1)//2 = 1.
    (n_g_d, _), (n_r_d, _) = _compute_cfar_radii(
        az_span=120.0,
        num_az_angles=61,
        profile=a2.Profile.PROFILE_6,
        step_length_m=0.1,
        num_points=3,
        az_guard_fwhm_factor=0.78,
        dist_guard_envelope_len_factor=10.0,  # absurdly large
        az_reference_fwhm_factor=0.78,
        dist_reference_envelope_len_factor=10.0,
    )
    assert n_g_d <= 1
    assert n_r_d <= 1


# -- _compute_peak_finding_radii ---------------------------------------


def test_compute_peak_finding_radii_returns_two_values():
    result = _compute_peak_finding_radii(
        az_span=120.0,
        num_az_angles=61,
        profile=a2.Profile.PROFILE_3,
        step_length_m=0.05,
        num_points=41,
        peak_finding_dist_radius_fwhm_factor=0.5,
        peak_finding_az_radius_fwhm_factor=0.5,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_config_az_angles_property():
    config = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        az_grid_resolution_deg=10.0,
        az_angle_range=(-60.0, 60.0),
    )
    angles = config.az_angles(_DEFAULT_VOLUME)
    assert config.num_az_angles(_DEFAULT_VOLUME) == 13
    assert len(angles) == 13
    assert angles[0] == -60.0
    assert angles[-1] == 60.0


def test_config_az_span_single_angle():
    # Span 0 -> num_az_angles == 1 regardless of resolution.
    config = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        az_grid_resolution_deg=10.0,
        az_angle_range=(0.0, 0.0),
    )
    assert config.num_az_angles(_DEFAULT_VOLUME) == 1
    assert config.az_span(_DEFAULT_VOLUME) == 0.0


def test_config_n_el_interpolation_cap():
    # el_grid_resolution_deg=None -> num_el_angles=1
    assert (
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212, el_grid_resolution_deg=None
        ).n_el_interpolation(_DEFAULT_VOLUME)
        == 0
    )
    # span 60° / 30° -> 2 intervals -> 3 angles
    assert (
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212,
            el_grid_resolution_deg=60.0,
            el_angle_range=(-30.0, 30.0),
        ).n_el_interpolation(_DEFAULT_VOLUME)
        == 0
    )
    assert (
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212,
            el_grid_resolution_deg=30.0,
            el_angle_range=(-30.0, 30.0),
        ).n_el_interpolation(_DEFAULT_VOLUME)
        == _N_EL_INTERPOLATION
    )


def test_config_get_cfar_radii_delegates():
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    radii = config.get_cfar_radii(
        _DEFAULT_VOLUME, a2.Profile.PROFILE_3, step_length_m=0.05, num_points=41
    )
    assert isinstance(radii, tuple)
    assert len(radii) == 2  # (guard, ref)
    assert all(len(r) == 2 for r in radii)  # each is (n_d, n_az)


def test_config_get_peak_finding_radii_delegates():
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    n_dist, n_az = config.get_peak_finding_radii(
        _DEFAULT_VOLUME, a2.Profile.PROFILE_3, step_length_m=0.05, num_points=41
    )
    assert n_dist >= 0
    assert n_az >= 0


# -- n_el cap rule (mirrored from processor) ---------------------------------


@pytest.mark.parametrize(
    "num_el_angles,expected",
    [(1, 0), (2, 0), (3, _N_EL_INTERPOLATION), (5, _N_EL_INTERPOLATION)],
)
def test_n_el_cap(num_el_angles, expected):
    n_el = _N_EL_INTERPOLATION if num_el_angles >= 3 else 0
    assert n_el == expected


# -- MotionDetectionConfig validators ----------------------------------------


def test_motion_config_default_constructs():
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    assert config.beamforming_method is BeamformingMethod.ROBUST_CAPON
    assert config.jitter_averaging_efficiency == pytest.approx(0.7)
    assert config.spatial_uncorr_jitter_factor == pytest.approx(0.1)


def test_motion_config_rejects_negative_filter_constant():
    with pytest.raises(ValueError):
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212, covariance_matrix_time_constant_s=-0.1
        )


def test_motion_config_rejects_jitter_efficiency_over_one():
    with pytest.raises(ValueError):
        MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212, jitter_averaging_efficiency=1.5)


def test_motion_config_rejects_all_drop_aggregate():
    with pytest.raises(ValueError):
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212,
            cfar_aggregate_method=(CFARAggregateMethod.DROP, CFARAggregateMethod.DROP),
        )


def test_motion_config_rejects_interp_radius_dist_factor_above_one():
    with pytest.raises(ValueError):
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212,
            peak_finding_dist_radius_fwhm_factor=1.1,
        )


def test_motion_config_rejects_interp_radius_az_factor_above_one():
    with pytest.raises(ValueError):
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212,
            peak_finding_az_radius_fwhm_factor=1.1,
        )


# -- to_dict / from_dict round-trip ------------------------------------------


def test_motion_config_round_trip_default():
    original = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    rebuilt = MotionDetectionConfig.from_dict(original.to_dict())
    assert rebuilt.beamforming_method is original.beamforming_method
    assert rebuilt.cfar_aggregate_method == original.cfar_aggregate_method
    assert rebuilt.detection_volume_x_bound_offset_m is None
    assert rebuilt.az_angle_range == original.az_angle_range


def test_motion_config_round_trip_with_bounds_as_list():
    """A list (from JSON) must be coerced back to a tuple."""
    original = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212, detection_volume_x_bound_offset_m=(-1.0, 1.0)
    )
    d = original.to_dict()
    d["detection_volume_x_bound_offset_m"] = list(d["detection_volume_x_bound_offset_m"])
    rebuilt = MotionDetectionConfig.from_dict(d)
    assert isinstance(rebuilt.detection_volume_x_bound_offset_m, tuple)
    assert rebuilt.detection_volume_x_bound_offset_m == (-1.0, 1.0)


def test_motion_config_json_round_trip_preserves_beamforming_method():
    original = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        beamforming_method=BeamformingMethod.ROBUST_CAPON,
    )
    rebuilt = MotionDetectionConfig.from_json(original.to_json())
    assert rebuilt.beamforming_method is BeamformingMethod.ROBUST_CAPON


def test_motion_config_json_round_trip_preserves_interpolation_method():
    original = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        peak_interpolation_az_dist_method=InterpolationMethod2D.NONE,
    )
    rebuilt = MotionDetectionConfig.from_json(original.to_json())
    assert rebuilt.peak_interpolation_az_dist_method is InterpolationMethod2D.NONE


# -- cfar_az FWHM factor -----------------------------------------------------


def test_cfar_az_factor_default_preserves_8_deg():
    """Default factor 0.78 × 10.2° ≈ 8° — should give the same cell count
    that an explicit 8° radius would have produced."""
    # num_az_angles=61, az_span=120° -> step 2°
    (_, n_g_a_factor), (_, n_r_a_factor) = _compute_cfar_radii(
        az_span=120.0,
        num_az_angles=61,
        profile=a2.Profile.PROFILE_3,
        step_length_m=0.05,
        num_points=41,
        az_guard_fwhm_factor=0.78,
        dist_guard_envelope_len_factor=0.5,
        az_reference_fwhm_factor=0.78,
        dist_reference_envelope_len_factor=0.25,
    )
    # 0.78 * 10.2 = 7.956°; on a 2°/cell grid that's round(3.978) = 4.
    # 8° on the same grid is round(4.0) = 4. Same.
    assert n_g_a_factor == 4
    assert n_r_a_factor == 4


def test_motion_config_rejects_cfar_az_guard_factor_above_two():
    with pytest.raises(ValueError):
        MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212, cfar_az_guard_fwhm_factor=2.5)


def test_motion_config_rejects_cfar_az_reference_factor_above_two():
    with pytest.raises(ValueError):
        MotionDetectionConfig(
            antenna_array=a2.AntennaArray.AP212, cfar_az_reference_fwhm_factor=2.5
        )


# -- Peak interpolation bin caps --------------------------------------------


def test_peak_interp_dist_clamps_to_two_bins():
    # Very dense distance grid -> factor 1.0 × FWHM would yield many bins.
    n_dist, _ = _compute_peak_finding_radii(
        az_span=120.0,
        num_az_angles=61,
        profile=a2.Profile.PROFILE_3,
        step_length_m=0.005,
        num_points=201,
        peak_finding_dist_radius_fwhm_factor=1.0,
        peak_finding_az_radius_fwhm_factor=0.5,
    )
    assert n_dist == _MAX_PEAK_FINDING_DIST_RADIUS_BINS


def test_peak_interp_az_clamps_to_three_bins():
    _, n_az = _compute_peak_finding_radii(
        az_span=120.0,
        num_az_angles=61,
        profile=a2.Profile.PROFILE_3,
        step_length_m=0.05,
        num_points=41,
        peak_finding_dist_radius_fwhm_factor=0.5,
        peak_finding_az_radius_fwhm_factor=1.0,  # 10.2° / 2°/cell = 5 bins uncapped
    )
    assert n_az == _MAX_PEAK_FINDING_AZ_RADIUS_BINS


def test_peak_interp_default_az_factor_lands_on_az_cap():
    """Default factor=0.5 + default az_grid_resolution_deg=2.0 (61 bins) should
    yield exactly _MAX_PEAK_FINDING_AZ_RADIUS_BINS = 3 (no clamping headroom)."""
    _, n_az = _compute_peak_finding_radii(
        az_span=120.0,
        num_az_angles=61,
        profile=a2.Profile.PROFILE_3,
        step_length_m=0.05,
        num_points=41,
        peak_finding_dist_radius_fwhm_factor=0.5,
        peak_finding_az_radius_fwhm_factor=0.5,
    )
    # 0.5 * 10.2 = 5.1°; on 2°/cell -> round(2.55) = 3.
    expected = round(0.5 * CONVENTIONAL_AZ_FWHM_DEG / (120.0 / 60.0))
    assert n_az == expected == _MAX_PEAK_FINDING_AZ_RADIUS_BINS


# -- MotionDetectionConfig.validate() ---------------------------------------


def _subsweep(step_length_m: float, num_points: int, profile: a2.Profile) -> a2.SubsweepConfig:
    return a2.SubsweepConfig(
        profile=profile,
        step_length=round(step_length_m / BASE_STEP_LENGTH_M),
        num_points=num_points,
    )


def _session_config(*subsweeps: a2.SubsweepConfig) -> a2.SessionConfig:
    sensor_config = a2.SensorConfig(
        subsweeps=list(subsweeps),
        sweeps_per_frame=1,
        sweep_rate=None,
        frame_rate=None,
        inter_frame_idle_state=a2.IdleState.ARMED,
        inter_sweep_idle_state=a2.IdleState.ARMED,
    )
    return a2.SessionConfig([sensor_config], update_rate=10.0)


def _validate_warnings(
    config: MotionDetectionConfig, session_config: a2.SessionConfig
) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config.validate(session_config, _DEFAULT_INSTALLATION, _DEFAULT_VOLUME)
    return [str(w.message) for w in caught]


def test_motion_config_validate_emits_warning_on_az_clamp():
    config = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        az_grid_resolution_deg=2.0,  # 61 bins on (-60, 60)
        az_angle_range=(-60.0, 60.0),
        peak_finding_az_radius_fwhm_factor=1.0,  # 5 bins uncapped
    )
    messages = _validate_warnings(
        config, _session_config(_subsweep(0.05, 41, a2.Profile.PROFILE_3))
    )
    assert any("peak_finding_az_radius_fwhm_factor" in m for m in messages)


def test_motion_config_validate_emits_warning_on_dist_clamp():
    config = MotionDetectionConfig(
        antenna_array=a2.AntennaArray.AP212,
        peak_finding_dist_radius_fwhm_factor=1.0,
    )
    messages = _validate_warnings(
        config, _session_config(_subsweep(0.005, 201, a2.Profile.PROFILE_3))
    )
    assert any("peak_finding_dist_radius_fwhm_factor" in m for m in messages)


def test_motion_config_validate_quiet_at_default_az_factor():
    """Default factor=0.5 + default az_grid_resolution_deg=2.0 lands exactly
    on the cap (uncapped = 3 = cap), so no clamping -> no warning."""
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    messages = _validate_warnings(
        config, _session_config(_subsweep(0.05, 41, a2.Profile.PROFILE_3))
    )
    assert not any("peak_finding" in m for m in messages)


def test_motion_config_validate_consistent_multi_subsweep_passes():
    """Two subsweeps with identical profile and step_length must not raise."""
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    ss = _subsweep(0.05, 20, a2.Profile.PROFILE_3)
    config.validate(
        _session_config(ss, ss), _DEFAULT_INSTALLATION, _DEFAULT_VOLUME
    )  # must not raise


def test_motion_config_validate_mismatched_profile_raises():
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    with pytest.raises(ValidationError, match="profile"):
        config.validate(
            _session_config(
                _subsweep(0.05, 20, a2.Profile.PROFILE_3),
                _subsweep(0.05, 20, a2.Profile.PROFILE_5),
            ),
            _DEFAULT_INSTALLATION,
            _DEFAULT_VOLUME,
        )


def test_motion_config_validate_mismatched_step_length_raises():
    config = MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212)
    with pytest.raises(ValidationError, match="step_length"):
        config.validate(
            _session_config(
                _subsweep(0.05, 20, a2.Profile.PROFILE_3),
                _subsweep(0.10, 20, a2.Profile.PROFILE_3),
            ),
            _DEFAULT_INSTALLATION,
            _DEFAULT_VOLUME,
        )
