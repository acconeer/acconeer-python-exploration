# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for WallMountSessionAbstractionConfig combined with SensorInstallation and
DetectionVolume."""

from __future__ import annotations

import math
import warnings

import attrs
import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from acconeer.exptool.a2._core.entities.configs.subsweep_config import (
    MAX_HWAAS,
    MAX_NUM_CHANNELS,
)
from acconeer.exptool.a2.algo import _rlg_correction as rlg_correction
from acconeer.exptool.a2.algo._detection_geometry import (
    DEFAULT_ROOM_HEIGHT_M,
    DetectionVolume,
    SensorInstallation,
)
from acconeer.exptool.a2.algo._shared_config import (
    WallMountSessionAbstractionConfig,
    _required_range_m,
    _rlg_correction_db_at,
    _WallMountSessionAbstractionConfig_v0,
    _WallMountSessionAbstractionConfig_v1,
    _WallMountSessionAbstractionConfig_v2,
    room_z_bounds_m,
    session_abstraction_config_timeline,
)
from acconeer.exptool.a2.algo._utils import (
    _PULSE_LENGTH_COMPENSATION_FACTOR,
    BASE_STEP_LENGTH_M,
    ENVELOPE_LENGTH_M,
    MEAN_BASE_RLG_DB,
    get_distances,
    get_distances_from_config,
    get_effective_frame_rate,
    hwaas_required,
)
from acconeer.exptool.a2.algo.motion_detection.config import (
    get_sitting_detection_configs,
    get_walking_detection_configs,
)
from acconeer.exptool.a2.algo.nodes._spherical_to_cartesian_nodes import RotationMatrix


# The sensor at the world origin, level, looking along +y.
_LEVEL_MOUNT = SensorInstallation(mount_height_m=1.5)


def _height_at_z(z_m: float) -> float:
    """snr_evaluation_height_m of the plane at world ``z_m``, for _LEVEL_MOUNT
    and other installations mounted as high."""
    return z_m + _LEVEL_MOUNT.mount_height_m


def _boresight_volume(start_m: float, end_m: float) -> DetectionVolume:
    """A box thin in x, along the boresight from ``start_m`` to ``end_m``.
    The box is as high as the room, so ``end_m`` cuts its far corners off:
    the range from the sensor is ``start_m`` to ``end_m``."""
    return DetectionVolume(x_bounds_m=(-0.001, 0.001), y_bounds_m=(start_m, end_m), end_m=end_m)


def _num_points_loop(
    config: WallMountSessionAbstractionConfig, detection_volume: DetectionVolume
) -> int:
    """Loop form of the closed-form ``num_points`` of ``_get_point_grid_bounds``,
    as a test oracle."""
    step_length = config._get_max_step_length()
    pulse_length_m = ENVELOPE_LENGTH_M[config.profile] / 2
    half_peak_length_m = pulse_length_m * _PULSE_LENGTH_COMPENSATION_FACTOR
    start_m, end_m = _required_range_m(_LEVEL_MOUNT, detection_volume)
    num_points = 1
    while (
        end_m / BASE_STEP_LENGTH_M - step_length / 2 - step_length * num_points
    ) * BASE_STEP_LENGTH_M >= max(half_peak_length_m, start_m):
        num_points += 1
    return num_points


def _az_el_deg(
    points_world_m: np.ndarray, installation: SensorInstallation
) -> tuple[np.ndarray, np.ndarray]:
    """(az_deg, el_deg) in the sensor frame for world points (same
    convention as ``_rlg_correction_db_at``)."""
    points_raw = installation.world_to_sensor(points_world_m)
    az = np.degrees(np.arctan2(points_raw[:, 0], np.hypot(points_raw[:, 1], points_raw[:, 2])))
    el = np.degrees(np.arctan2(points_raw[:, 2], points_raw[:, 1]))
    return az, el


def _oracle_processing_gain_db(config: WallMountSessionAbstractionConfig) -> float:
    """Processing gain ``hwaas_required`` expects, written out independently
    of the config's own helpers: coherent combination of all channels plus
    covariance-averaged sweeps."""
    return float(10.0 * np.log10(MAX_NUM_CHANNELS) + 5.0 * np.log10(config.sweeps_per_frame))


def _dense_box_points_m(
    installation: SensorInstallation, volume: DetectionVolume, resolution_m: float
) -> np.ndarray:
    """Dense ``(N, 3)`` grid of points filling ``volume``'s box, as high as
    ``installation``'s room, in the world frame. Independent of the config's
    own sampling, so it can serve as a test oracle."""
    axes = [
        np.linspace(lo, hi, max(2, int(np.ceil((hi - lo) / resolution_m)) + 1))
        for lo, hi in (
            volume.x_bounds_m,
            volume.y_bounds_m,
            room_z_bounds_m(installation),
        )
    ]
    return np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)


def _in_fov_mask(
    installation: SensorInstallation, volume: DetectionVolume, points_world_m: np.ndarray
) -> np.ndarray:
    """``True`` for points within ``az_angle_range``/``el_angle_range``, the
    only points ``get_session_config`` guarantees SNR for."""
    az, el = _az_el_deg(points_world_m, installation)
    az_lo, az_hi = volume.az_angle_range
    el_lo, el_hi = volume.el_angle_range
    return (az >= az_lo) & (az <= az_hi) & (el >= el_lo) & (el <= el_hi)


def _achieved_snr_db(
    config: WallMountSessionAbstractionConfig,
    session_config: a2.SessionConfig,
    points_world_m: np.ndarray,
    installation: SensorInstallation,
) -> np.ndarray:
    """Recompute achieved SNR from a derived session config at arbitrary
    world points, via the same link budget used to derive it -- the
    end-to-end oracle for the "never under-provision" property."""
    distances, hwaas_chunks = [], []
    for subsweep in session_config.sensor_config.subsweeps:
        distances.append(get_distances_from_config(subsweep))
        hwaas_chunks.append(subsweep.hwaas_points)
    distances_m = np.concatenate(distances)
    hwaas_points = np.concatenate(hwaas_chunks)

    r = np.linalg.norm(points_world_m, axis=-1)
    az, el = _az_el_deg(points_world_m, installation)

    nearest_idx = np.argmin(np.abs(distances_m[:, None] - r[None, :]), axis=0)
    achieved_hwaas = hwaas_points[nearest_idx]
    channel_gain_db = 10 * np.log10(12)
    sweep_gain_db = 5 * np.log10(config.sweeps_per_frame)
    return (
        10 * np.log10(achieved_hwaas)
        + MEAN_BASE_RLG_DB[config.profile]
        + rlg_correction.rlg_correction_db(az, el)
        + channel_gain_db
        + sweep_gain_db
        - 40 * np.log10(r)
    )


@pytest.mark.parametrize("profile", list(ENVELOPE_LENGTH_M.keys()))
@pytest.mark.parametrize("start_m", [0.5, 1.0, 2.0])
@pytest.mark.parametrize("end_m", [3.0, 5.0, 8.0])
def test_num_points_matches_loop(profile, start_m, end_m):
    if start_m >= end_m:
        pytest.skip("invalid combination")
    volume = _boresight_volume(start_m, end_m)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=profile,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    _, num_points = config._get_point_grid_bounds(_LEVEL_MOUNT, volume)
    assert num_points == _num_points_loop(config, volume)


def test_num_points_floor_is_one():
    # Tiny range: the closed form gives 0, which is floored to 1.
    volume = _boresight_volume(0.0, 0.01)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_1,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    _, num_points = config._get_point_grid_bounds(_LEVEL_MOUNT, volume)
    assert num_points == 1


def test_volume_rejects_range_above_max():
    with pytest.raises(ValueError):
        _boresight_volume(0.0, 15.0)


def test_validators_reject_zero_frame_rate():
    with pytest.raises(ValueError):
        WallMountSessionAbstractionConfig(
            signal_quality_db=20.5,
            profile=a2.Profile.PROFILE_3,
            frame_rate=0.0,
            snr_evaluation_height_m=_height_at_z(-0.8),
            sweep_rate=None,
        )


def test_validators_reject_zero_signal_quality_db():
    with pytest.raises(ValueError):
        WallMountSessionAbstractionConfig(
            signal_quality_db=0.0,
            profile=a2.Profile.PROFILE_3,
            frame_rate=10.0,
            snr_evaluation_height_m=_height_at_z(-0.8),
            sweep_rate=None,
        )


def test_validators_reject_max_num_subsweeps_above_hardware_cap():
    with pytest.raises(ValueError):
        WallMountSessionAbstractionConfig(
            signal_quality_db=20.5,
            profile=a2.Profile.PROFILE_3,
            frame_rate=10.0,
            max_num_subsweeps=a2.SensorConfig.MAX_NUM_SUBSWEEPS + 1,
            snr_evaluation_height_m=_height_at_z(-0.8),
            sweep_rate=None,
        )


def test_validators_reject_max_num_subsweeps_at_old_hardware_cap():
    # SensorConfig.MAX_NUM_SUBSWEEPS (5) itself must be rejected too:
    # jitter_compensation is hardcoded True in _make_sensor_config, which
    # reserves one subsweep slot, so the real cap is MAX_NUM_SUBSWEEPS - 1.
    with pytest.raises(ValueError):
        WallMountSessionAbstractionConfig(
            signal_quality_db=20.5,
            profile=a2.Profile.PROFILE_3,
            frame_rate=10.0,
            max_num_subsweeps=a2.SensorConfig.MAX_NUM_SUBSWEEPS,
            snr_evaluation_height_m=_height_at_z(-0.8),
            sweep_rate=None,
        )


def test_validate_raises_on_frame_rate_above_max():
    volume = _boresight_volume(1.0, 5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1000.0,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    with pytest.raises(ValidationError, match=r"frame_rate.*exceeds the maximum frame rate"):
        config.validate(_LEVEL_MOUNT, volume)


def test_validate_accepts_frame_rate_below_max():
    volume = _boresight_volume(1.0, 5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=0.5,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    config.validate(_LEVEL_MOUNT, volume)


def test_validate_raises_on_sweep_rate_above_max():
    volume = _boresight_volume(1.0, 5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=0.5,
        sweep_rate=1_000_000.0,
        snr_evaluation_height_m=_height_at_z(0.0),
    )
    with pytest.raises(ValidationError, match=r"sweep_rate.*exceeds the maximum"):
        config.validate(_LEVEL_MOUNT, volume)


def test_validate_skips_sweep_rate_check_when_none():
    # sweep_rate=None means "let the sensor pick" — no check should fire.
    volume = _boresight_volume(1.0, 5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=0.5,
        sweep_rate=None,
        snr_evaluation_height_m=_height_at_z(0.0),
    )
    config.validate(_LEVEL_MOUNT, volume)


def test_get_session_config_applies_armed_idle_states():
    volume = _boresight_volume(0.5, 1.5)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(0.0),  # through the volume, at sensor height
        sweep_rate=None,
    )
    session = config.get_session_config(_LEVEL_MOUNT, volume)
    sensor = session.sensor_config
    assert 1 <= len(sensor.subsweeps) <= config.max_num_subsweeps
    assert sensor.jitter_compensation is True
    assert sensor.inter_frame_idle_state is a2.IdleState.ARMED
    assert sensor.inter_sweep_idle_state is a2.IdleState.ARMED


def test_get_session_config_never_exceeds_max_num_subsweeps():
    # A long, demanding range that would want many subsweeps if unbounded.
    volume = DetectionVolume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(0.3, 8.0))
    for max_num_subsweeps in (1, 2, 3, 4):
        config = WallMountSessionAbstractionConfig(
            signal_quality_db=30.0,
            profile=a2.Profile.PROFILE_5,
            frame_rate=1.0,
            max_num_subsweeps=max_num_subsweeps,
            snr_evaluation_height_m=_height_at_z(-0.8),
            sweep_rate=None,
        )
        session = config.get_session_config(_LEVEL_MOUNT, volume)
        assert len(session.sensor_config.subsweeps) <= max_num_subsweeps


def test_default_session_config_is_never_invalid_per_sensor_config_validate():
    """The same demanding volume as test_get_session_config_never_exceeds_max_num_subsweeps,
    at the *default* max_num_subsweeps: jitter_compensation is hardcoded True
    in _make_sensor_config, which reserves one subsweep slot, so the DP must
    never be allowed to use every hardware slot (SensorConfig.MAX_NUM_SUBSWEEPS)
    -- SensorConfig's own validate() is the ground truth for that rule."""
    volume = DetectionVolume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(0.3, 8.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=30.0,
        profile=a2.Profile.PROFILE_5,
        frame_rate=1.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    session = config.get_session_config(_LEVEL_MOUNT, volume)
    assert len(session.sensor_config.subsweeps) == config.max_num_subsweeps
    session.sensor_config.validate()  # must not raise


def test_get_session_config_subsweeps_share_profile_and_step_length():
    volume = DetectionVolume(x_bounds_m=(-2.0, 2.0), y_bounds_m=(0.3, 6.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=32.0,
        profile=a2.Profile.PROFILE_5,
        frame_rate=1.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    session = config.get_session_config(_LEVEL_MOUNT, volume)
    subsweeps = session.sensor_config.subsweeps
    assert len({ss.profile for ss in subsweeps}) == 1
    assert len({ss.step_length for ss in subsweeps}) == 1


def test_closed_form_math_is_consistent():
    """Spot-check: closed form returns ``max(1, floor(K) + 1)`` where
    ``K = (end - threshold) / (step * B) - 0.5``."""
    volume = _boresight_volume(0.5, 4.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    step = config._get_max_step_length()
    start_m, end_m = _required_range_m(_LEVEL_MOUNT, volume)
    threshold = max(
        ENVELOPE_LENGTH_M[config.profile] / 2 * _PULSE_LENGTH_COMPENSATION_FACTOR, start_m
    )
    k = (end_m - threshold) / (step * BASE_STEP_LENGTH_M) - 0.5
    _, num_points = config._get_point_grid_bounds(_LEVEL_MOUNT, volume)
    assert num_points == max(1, math.floor(k) + 1)


def test_validate_emits_warning_on_hwaas_saturation():
    volume = _boresight_volume(0.5, 8.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=100.0,  # absurd -> saturates the HWAAS hardware cap
        profile=a2.Profile.PROFILE_3,
        frame_rate=0.01,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config.validate(_LEVEL_MOUNT, volume)
    messages = [str(w.message) for w in caught]
    assert any("Decrease signal quality" in m for m in messages)
    assert any("Shrink the detection volume" in m for m in messages)
    assert any(
        ss.hwaas_max >= MAX_HWAAS
        for ss in config.get_session_config(_LEVEL_MOUNT, volume).sensor_config.subsweeps
    )


def test_validate_quiet_when_hwaas_is_feasible():
    volume = _boresight_volume(0.5, 2.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config.validate(_LEVEL_MOUNT, volume)
    assert not any("Decrease signal quality" in str(w.message) for w in caught)
    assert not any("Shrink the detection volume" in str(w.message) for w in caught)


def _infeasible_configuration_messages(
    results: list[ValidationResult],
) -> list[ValidationResult]:
    return [
        r
        for r in results
        if isinstance(r, ValidationWarning)
        and ("Decrease signal quality" in r.message or "Shrink the detection volume" in r.message)
    ]


def test_infeasible_frame_rate_warns_on_signal_quality_and_volume_once_each():
    """frame_rate above the modeled maximum frame rate -- infeasible for a
    reason other than HWAAS saturation -- still gets the pair of
    user-facing warnings, exactly once each."""
    volume = _boresight_volume(1.0, 5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1000.0,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    results = config._collect_validation_results(_LEVEL_MOUNT, volume)

    infeasible = _infeasible_configuration_messages(results)
    assert sum(r.aspect == "signal_quality_db" for r in infeasible) == 1
    assert sum(r.aspect == "y_bounds_m" for r in infeasible) == 1
    assert all(r.source is config for r in infeasible if r.aspect == "signal_quality_db")
    assert all(r.source is volume for r in infeasible if r.aspect == "y_bounds_m")

    # The existing frame_rate error is unchanged.
    assert any(isinstance(r, ValidationError) and r.aspect == "frame_rate" for r in results)


def test_hwaas_saturation_warns_on_signal_quality_and_volume_once_each():
    volume = _boresight_volume(0.5, 8.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=100.0,  # absurd -> saturates the HWAAS hardware cap
        profile=a2.Profile.PROFILE_3,
        frame_rate=0.01,
        sweeps_per_frame=8,  # isolate the HWAAS-saturation check from rate feasibility
        sweep_rate=None,
        snr_evaluation_height_m=_height_at_z(0.0),
    )
    results = config._collect_validation_results(_LEVEL_MOUNT, volume)

    infeasible = _infeasible_configuration_messages(results)
    assert sum(r.aspect == "signal_quality_db" for r in infeasible) == 1
    assert sum(r.aspect == "y_bounds_m" for r in infeasible) == 1

    # No frame_rate/sweep_rate feasibility error here: only HWAAS saturates.
    assert not any(isinstance(r, ValidationError) for r in results)


def test_infeasible_configuration_without_a_box_points_at_end_m():
    """A volume without a box is sized by end_m, so the volume warning
    goes there."""
    volume = DetectionVolume(end_m=5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1000.0,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    results = config._collect_validation_results(_LEVEL_MOUNT, volume)

    infeasible = _infeasible_configuration_messages(results)
    assert [r.aspect for r in infeasible if r.source is volume] == ["end_m"]


def test_frame_rate_is_in_the_advanced_pidget_group():
    from acconeer.exptool.a2.algo._shared_pidget_mapping import (
        get_session_abstraction_pidget_mapping,
    )
    from acconeer.exptool.app.new.ui import pidgets

    mapping = get_session_abstraction_pidget_mapping()
    for group, factories in mapping.items():
        if "frame_rate" in factories:
            assert isinstance(group, pidgets.CollapsiblePidgetGroup)
            return
    pytest.fail("frame_rate not found in any pidget group")


def test_collect_validation_results_does_not_raise_for_out_of_range_volume():
    # Farthest corner sqrt(8^2 + 8^2 + 1.5^2) > MAX_RANGE_M while every axis is
    # within range on its own, so only the range check catches it.
    volume = DetectionVolume(x_bounds_m=(-8.0, 8.0), y_bounds_m=(0.0, 8.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    assert volume._collect_validation_results() == []
    results = config._collect_validation_results(_LEVEL_MOUNT, volume)
    assert len(results) == 1 and isinstance(results[0], ValidationError)
    assert results[0].source is volume and results[0].aspect == "end_m"


@pytest.mark.parametrize(
    "unusable_volume",
    [
        # Out of range: farthest corner beyond MAX_RANGE_M.
        DetectionVolume(x_bounds_m=(-8.0, 8.0), y_bounds_m=(0.0, 8.0)),
        # end_m short of the box.
        DetectionVolume(x_bounds_m=(-2.5, 2.5), y_bounds_m=(5.0, 7.5), end_m=4.0),
    ],
)
def test_try_get_session_config_is_none_when_get_session_config_raises(unusable_volume):
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    usable_volume = DetectionVolume(x_bounds_m=(-2.5, 2.5), y_bounds_m=(0.5, 7.5))

    assert config.try_get_session_config(_LEVEL_MOUNT, usable_volume) == config.get_session_config(
        _LEVEL_MOUNT, usable_volume
    )
    with pytest.raises(ValidationError):
        config.get_session_config(_LEVEL_MOUNT, unusable_volume)
    assert config.try_get_session_config(_LEVEL_MOUNT, unusable_volume) is None


def test_get_session_config_is_deterministic():
    volume = DetectionVolume(x_bounds_m=(-2.5, 2.5), y_bounds_m=(0.5, 7.5))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=32.0,
        profile=a2.Profile.PROFILE_6,
        frame_rate=0.5,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    session_a = config.get_session_config(_LEVEL_MOUNT, volume)
    session_b = config.get_session_config(_LEVEL_MOUNT, volume)
    assert session_a.sensor_config.subsweeps == session_b.sensor_config.subsweeps


def test_get_session_config_ignores_points_outside_angle_range():
    """A wide, shallow volume whose corners lie outside a narrowed
    az_angle_range needs less HWAAS than the same volume under the default
    az_angle_range: excluded angles are not provisioned for.

    An evaluation plane at sensor height puts every plane point at el=0, so only
    az_angle_range limits the observable points.
    """
    volume_narrow_fov = DetectionVolume(
        x_bounds_m=(-4.0, 4.0),
        y_bounds_m=(0.5, 1.0),
        az_angle_range=(-10.0, 10.0),
    )
    volume_default_fov = DetectionVolume(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.5, 1.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=32.0,
        profile=a2.Profile.PROFILE_6,
        frame_rate=0.5,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )

    hwaas_max_narrow = max(
        ss.hwaas_max
        for ss in config.get_session_config(
            _LEVEL_MOUNT, volume_narrow_fov
        ).sensor_config.subsweeps
    )
    hwaas_max_default = max(
        ss.hwaas_max
        for ss in config.get_session_config(
            _LEVEL_MOUNT, volume_default_fov
        ).sensor_config.subsweeps
    )
    assert hwaas_max_narrow < hwaas_max_default


def test_get_session_config_never_under_provisions_at_snr_evaluation_plane():
    """Achieved SNR, recomputed from the returned session config via the
    link budget at independently sampled points, never falls below
    signal_quality_db (small tolerance for floating point).

    Points are sampled on the snr_evaluation_height_m plane within
    az_angle_range/el_angle_range, where get_session_config guarantees SNR.
    """
    volume = DetectionVolume(x_bounds_m=(-2.5, 2.5), y_bounds_m=(0.5, 7.5))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=32.0,
        profile=a2.Profile.PROFILE_6,
        frame_rate=0.5,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    session = config.get_session_config(_LEVEL_MOUNT, volume)

    rng = np.random.default_rng(1234)
    n = 20000
    points = np.stack(
        [
            rng.uniform(*volume.x_bounds_m, n),
            rng.uniform(*volume.y_bounds_m, n),
            np.full(n, config._snr_evaluation_z_m(_LEVEL_MOUNT)),
        ],
        axis=-1,
    )
    points = points[_in_fov_mask(_LEVEL_MOUNT, volume, points)]
    achieved_snr = _achieved_snr_db(config, session, points, _LEVEL_MOUNT)
    assert achieved_snr.min() >= config.signal_quality_db - 0.5


def test_snr_evaluation_height_m_defaults_to_chest_height_and_is_bounded():
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        sweep_rate=None,
    )
    assert config.snr_evaluation_height_m == 1.2
    for height_m in (-0.1, 10.1):
        with pytest.raises(ValueError):
            attrs.evolve(config, snr_evaluation_height_m=height_m)


def test_z_plane_restriction_reduces_required_hwaas_vs_full_box():
    """Restricting the guarantee to the snr_evaluation_height_m plane needs less
    HWAAS than guaranteeing across the box's full height would, as the box
    reaches well past that plane (driving elevation further from boresight
    than the single plane does)."""
    volume = DetectionVolume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(0.5, 2.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )

    start_point, num_points = config._get_point_grid_bounds(_LEVEL_MOUNT, volume)
    step_length = config._get_max_step_length()
    distances_m = get_distances(start_point, step_length, num_points)

    z_plane_required = config._required_hwaas_curve(_LEVEL_MOUNT, volume, distances_m)

    # Reference: the same requirement over the full box, at every z.
    points_world = _dense_box_points_m(_LEVEL_MOUNT, volume, 0.05)
    r_all = np.linalg.norm(points_world, axis=-1)
    az_all, el_all = _az_el_deg(points_world, _LEVEL_MOUNT)
    az_lo, az_hi = volume.az_angle_range
    el_lo, el_hi = volume.el_angle_range
    in_fov = (az_all >= az_lo) & (az_all <= az_hi) & (el_all >= el_lo) & (el_all <= el_hi)
    r_all, az_all, el_all = r_all[in_fov], az_all[in_fov], el_all[in_fov]
    needed = hwaas_required(
        r_all,
        config.signal_quality_db,
        config.profile,
        rlg_correction_db=rlg_correction.rlg_correction_db(az_all, el_all),
        processing_gain_db=_oracle_processing_gain_db(config),
    )
    bin_idx = np.argmin(np.abs(distances_m[:, None] - r_all[None, :]), axis=0)
    full_box_required = np.full(len(distances_m), -np.inf)
    np.maximum.at(full_box_required, bin_idx, needed.astype(float))

    assert np.max(z_plane_required) < np.max(full_box_required)


@pytest.mark.parametrize(
    "x_rot,y_rot,z_rot",
    [(0.0, 0.0, 0.0), (15.0, 0.0, -10.0), (-30.0, 25.0, 20.0), (45.0, -60.0, 35.0)],
)
def test_rlg_correction_db_at_matches_inverse_rotated_reference(x_rot, y_rot, z_rot):
    """Reference angles come from ``R.T @ p``. The FOV is asymmetric in az and
    el, so a rotation applied in the wrong direction also changes
    ``observable``, not only ``correction_db``."""
    installation = SensorInstallation(
        x_rotation=x_rot, y_rotation=y_rot, z_rotation=z_rot, mount_height_m=1.5
    )
    volume = DetectionVolume(
        x_bounds_m=(-4.0, 4.0),
        y_bounds_m=(0.0, 6.0),
        az_angle_range=(-50.0, 20.0),
        el_angle_range=(-30.0, 10.0),
    )
    x_m = np.array([[-3.0, 0.0, 2.5], [1.0, -0.5, 3.5]])
    y_m = np.array([[1.5, 4.0, 5.0], [2.0, 3.0, 1.0]])
    z_m = -0.8

    correction_db, observable = _rlg_correction_db_at(installation, volume, x_m, y_m, z_m)

    points_world = np.stack([x_m, y_m, np.full_like(x_m, z_m)], axis=-1).reshape(-1, 3)
    rotation_matrix = RotationMatrix(x_deg=x_rot, y_deg=y_rot, z_deg=z_rot).matrix
    points_sensor = points_world @ rotation_matrix  # R.T @ p for each point
    ref_az = np.degrees(
        np.arctan2(points_sensor[:, 0], np.hypot(points_sensor[:, 1], points_sensor[:, 2]))
    )
    ref_el = np.degrees(np.arctan2(points_sensor[:, 2], points_sensor[:, 1]))
    assert correction_db.shape == observable.shape == x_m.shape
    np.testing.assert_allclose(
        correction_db.ravel(), rlg_correction.rlg_correction_db(ref_az, ref_el), atol=1e-9
    )
    # Every point lies inside the box, so observable reduces to the FOV check.
    (az_lo, az_hi), (el_lo, el_hi) = volume.az_angle_range, volume.el_angle_range
    np.testing.assert_array_equal(
        observable.ravel(),
        (ref_az >= az_lo) & (ref_az <= az_hi) & (ref_el >= el_lo) & (ref_el <= el_hi),
    )


def _fine_brute_force_required_hwaas(
    config: WallMountSessionAbstractionConfig,
    installation: SensorInstallation,
    volume: DetectionVolume,
    distances_m: np.ndarray,
    num_theta: int = 100_000,
) -> np.ndarray:
    """Test oracle for ``_required_hwaas_curve``: a single very fine
    full-circle scan per ``distances_m`` point, fine enough to approximate
    the continuous worst case within a tight tolerance."""
    z_eval = config._snr_evaluation_z_m(installation)
    rho_sq = distances_m**2 - z_eval**2
    feasible_r = rho_sq >= 0.0
    rho = np.sqrt(np.clip(rho_sq, 0.0, None))

    rotation_matrix = RotationMatrix(
        x_deg=installation.x_rotation, y_deg=installation.y_rotation, z_deg=installation.z_rotation
    ).matrix
    x_lo, x_hi = volume.x_bounds_m
    y_lo, y_hi = volume.y_bounds_m
    az_lo, az_hi = volume.az_angle_range
    el_lo, el_hi = volume.el_angle_range

    theta = np.linspace(0.0, 2.0 * np.pi, num_theta, endpoint=False)
    x = rho[:, None] * np.cos(theta)[None, :]
    y = rho[:, None] * np.sin(theta)[None, :]
    points_raw = np.stack([x, y, np.full_like(x, z_eval)], axis=-1) @ rotation_matrix
    xr, yr, zr = points_raw[..., 0], points_raw[..., 1], points_raw[..., 2]
    az = np.degrees(np.arctan2(xr, np.hypot(yr, zr)))
    el = np.degrees(np.arctan2(zr, yr))

    in_box = (x >= x_lo) & (x <= x_hi) & (y >= y_lo) & (y <= y_hi) & feasible_r[:, None]
    in_fov = (az >= az_lo) & (az <= az_hi) & (el >= el_lo) & (el <= el_hi)
    valid = in_box & in_fov

    needed = hwaas_required(
        distances_m,
        config.signal_quality_db,
        config.profile,
        rlg_correction_db=np.min(
            np.where(valid, rlg_correction.rlg_correction_db(az, el), np.inf), axis=1
        ),
        processing_gain_db=_oracle_processing_gain_db(config),
    )
    row_has_any = np.any(valid, axis=1)
    required = np.where(row_has_any, needed.astype(float), -np.inf)
    is_empty = np.isneginf(required)
    if np.any(is_empty) and np.any(~is_empty):
        filled_idx = np.flatnonzero(~is_empty)
        interpolated_log = np.interp(
            np.arange(len(required)), filled_idx, np.log(required[filled_idx])
        )
        required[is_empty] = np.ceil(np.exp(interpolated_log[is_empty]))
    return required


def _distances_m_for(
    config: WallMountSessionAbstractionConfig, volume: DetectionVolume
) -> np.ndarray:
    start_point, num_points = config._get_point_grid_bounds(_LEVEL_MOUNT, volume)
    step_length = config._get_max_step_length()
    return get_distances(start_point, step_length, num_points)


def test_required_hwaas_curve_handles_thin_arc_near_box_corner():
    """A box whose farthest distances_m point lies close to its diagonal
    corner distance, where the in-box arc is a fraction of a degree wide
    (see ``_edge_crossing_xy``). The shipped presets
    have this shape at their farthest point."""
    volume = DetectionVolume(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.0, 6.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=15.0,
        profile=a2.Profile.PROFILE_7,
        frame_rate=15.0,
        snr_evaluation_height_m=_height_at_z(-0.8),
        sweep_rate=None,
    )
    distances_m = _distances_m_for(config, volume)

    shipped = config._required_hwaas_curve(_LEVEL_MOUNT, volume, distances_m)
    oracle = _fine_brute_force_required_hwaas(config, _LEVEL_MOUNT, volume, distances_m)

    assert np.all(shipped >= oracle - 1)  # +-1 HWAAS: ceil()/discretization slop only


def test_required_hwaas_curve_handles_disjoint_feasible_arcs():
    """A box entirely off to one side of the sensor, spanning both in front
    of and behind it: at some ranges the circle-box intersection is two
    disjoint arcs (one on each side of the box), not one contiguous arc."""
    volume = DetectionVolume(
        x_bounds_m=(-3.0, -0.3),
        y_bounds_m=(-3.0, 3.0),
        az_angle_range=(-80.0, 80.0),
        el_angle_range=(-80.0, 80.0),
    )
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=22.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=5.0,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    distances_m = _distances_m_for(config, volume)

    shipped = config._required_hwaas_curve(_LEVEL_MOUNT, volume, distances_m)
    oracle = _fine_brute_force_required_hwaas(config, _LEVEL_MOUNT, volume, distances_m)

    assert np.all(shipped >= oracle - 1)


def test_required_hwaas_curve_fills_range_below_evaluation_plane():
    """No point on the evaluation plane is closer than its distance below the
    sensor, |z_eval_m|;
    distances_m points below that are filled from their nearest reachable
    neighbor."""
    volume = _boresight_volume(0.05, 3.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1.0,
        snr_evaluation_height_m=_height_at_z(-1.0),
        sweep_rate=None,
    )
    distances_m = _distances_m_for(config, volume)
    assert distances_m[0] < 1.0  # some points genuinely closer than the plane

    required = config._required_hwaas_curve(_LEVEL_MOUNT, volume, distances_m)
    assert np.all(np.isfinite(required))
    assert np.all(required > 0)


def test_required_hwaas_curve_raises_when_entirely_unreachable():
    """The evaluation plane above the box's reachable envelope: every
    distances_m point is empty, which raises a ValidationError."""
    volume = DetectionVolume(x_bounds_m=(-0.5, 0.5), y_bounds_m=(0.5, 1.0))
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1.0,
        snr_evaluation_height_m=DEFAULT_ROOM_HEIGHT_M,
        sweep_rate=None,
    )
    distances_m = _distances_m_for(config, volume)
    with pytest.raises(ValidationError, match="snr_evaluation_height_m plane"):
        config._required_hwaas_curve(_LEVEL_MOUNT, volume, distances_m)


def _plane_outside_fov_configs() -> tuple[
    WallMountSessionAbstractionConfig, SensorInstallation, DetectionVolume
]:
    """Sensor tilted 45 degrees down, evaluation plane at sensor height: every
    point on the plane sits at native el = +45 degrees, outside the default
    el_angle_range (-30, 30), although the plane runs through the box."""
    installation = SensorInstallation(x_rotation=-45.0, mount_height_m=1.5)
    volume = DetectionVolume(
        x_bounds_m=(-2.0, 2.0),
        y_bounds_m=(0.5, 4.0),
    )
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_5,
        frame_rate=1.0,
        snr_evaluation_height_m=_height_at_z(0.0),
        sweep_rate=None,
    )
    return config, installation, volume


def test_get_session_config_raises_when_plane_never_enters_fov():
    """The plane is inside the box but never inside the FOV: there is no
    observable point to guarantee SNR for, so the configuration is
    rejected."""
    config, installation, volume = _plane_outside_fov_configs()
    with pytest.raises(ValidationError, match="az_angle_range/el_angle_range") as exc_info:
        config.get_session_config(installation, volume)
    assert exc_info.value.aspect == "snr_evaluation_height_m"


def test_validation_reports_plane_outside_fov_as_error():
    config, installation, volume = _plane_outside_fov_configs()
    errors = [
        result
        for result in config._collect_validation_results(installation, volume)
        if isinstance(result, ValidationError)
    ]
    assert [error.aspect for error in errors] == ["snr_evaluation_height_m"]


# _LEVEL_MOUNT's room runs from the floor, 1.5 m below the sensor, up to 1.0 m
# above it.
_BOX_VOLUME = DetectionVolume(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.0, 6.0))


def _plane_config(z_m: float) -> WallMountSessionAbstractionConfig:
    return WallMountSessionAbstractionConfig(
        signal_quality_db=22.0,
        profile=a2.Profile.PROFILE_7,
        frame_rate=15.0,
        snr_evaluation_height_m=_height_at_z(z_m),
        sweep_rate=None,
    )


def test_snr_evaluation_height_is_capped_at_the_room_height():
    config = _plane_config(0.0)
    attrs.evolve(config, snr_evaluation_height_m=DEFAULT_ROOM_HEIGHT_M)
    with pytest.raises(ValueError, match="snr_evaluation_height_m"):
        attrs.evolve(config, snr_evaluation_height_m=DEFAULT_ROOM_HEIGHT_M + 0.01)


@pytest.mark.parametrize("z_m", [-1.5, 1.0])
def test_get_session_config_accepts_plane_on_the_floor_or_ceiling(z_m):
    _plane_config(z_m).get_session_config(_LEVEL_MOUNT, _BOX_VOLUME)


@pytest.mark.parametrize(
    "get_configs",
    [
        get_walking_detection_configs,
        get_sitting_detection_configs,
    ],
)
def test_shipped_presets_validate_without_errors_or_warnings(get_configs):
    _processor_config, session_abstraction_config, sensor_installation, detection_volume = (
        get_configs()
    )
    results = session_abstraction_config._collect_validation_results(
        sensor_installation, detection_volume
    )
    assert results == []


@pytest.mark.parametrize(
    "serialize",
    [_WallMountSessionAbstractionConfig_v0.to_dict, _WallMountSessionAbstractionConfig_v0.to_json],
)
def test_migration_from_v0_maps_min_of_close_and_far_to_signal_quality_db(serialize):
    """Old two-zone recordings load with signal_quality_db set to the lower
    of the two old SNR targets. The other fields carry over, except
    signal_quality_break_point_m and hwaas_min, which are dropped."""
    old = _WallMountSessionAbstractionConfig_v0(
        signal_quality_break_point_m=4.0,
        profile=a2.Profile.PROFILE_3,
        update_rate=12.0,
        max_snr_drop_db=2.0,
        signal_quality_close_db=32.0,
        signal_quality_far_db=26.0,
        hwaas_min=4,
        sweeps_per_frame=10,
        sweep_rate=500.0,
        receiver_gain=7,
    )

    migrated = session_abstraction_config_timeline.migrate(
        serialize(old), completer=lambda _: _LEVEL_MOUNT
    )

    assert isinstance(migrated, WallMountSessionAbstractionConfig)
    assert migrated.signal_quality_db == min(
        old.signal_quality_close_db, old.signal_quality_far_db
    )
    assert migrated.profile == old.profile
    assert migrated.frame_rate == old.update_rate
    assert migrated.max_snr_drop_db == old.max_snr_drop_db
    assert not hasattr(migrated, "hwaas_min")
    assert migrated.sweeps_per_frame == old.sweeps_per_frame
    assert migrated.sweep_rate == old.sweep_rate
    assert migrated.receiver_gain == old.receiver_gain


def test_migration_from_v0_sets_unmapped_fields():
    """max_num_subsweeps and the evaluation plane have no old-side equivalent:
    migration puts the plane at sensor height and allows the maximum number
    of subsweeps."""
    old = _WallMountSessionAbstractionConfig_v0(
        signal_quality_break_point_m=1.0, profile=a2.Profile.PROFILE_1, update_rate=5.0
    )

    migrated = session_abstraction_config_timeline.migrate(
        old.to_json(), completer=lambda _: _LEVEL_MOUNT
    )

    assert migrated.max_num_subsweeps == a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1
    assert migrated.snr_evaluation_height_m == _LEVEL_MOUNT.mount_height_m


def test_migrate_leaves_already_new_format_unchanged():
    """A recording in the current format loads back unchanged."""
    current = WallMountSessionAbstractionConfig(
        signal_quality_db=27.5,
        profile=a2.Profile.PROFILE_5,
        frame_rate=8.0,
        max_num_subsweeps=3,
        snr_evaluation_height_m=1.0,
        sweep_rate=None,
    )

    migrated = session_abstraction_config_timeline.migrate(current.to_json())

    assert migrated == current


@pytest.mark.parametrize(
    "serialize",
    [_WallMountSessionAbstractionConfig_v1.to_dict, _WallMountSessionAbstractionConfig_v1.to_json],
)
def test_migrate_reads_update_rate_as_frame_rate(serialize):
    """A config saved while the session was timed by update_rate loads with
    that rate as frame_rate."""
    old = _WallMountSessionAbstractionConfig_v1(
        signal_quality_db=27.5,
        profile=a2.Profile.PROFILE_5,
        update_rate=8.0,
        snr_evaluation_z_m=-0.5,
        sweep_rate=None,
    )

    migrated = session_abstraction_config_timeline.migrate(
        serialize(old), completer=lambda _: _LEVEL_MOUNT
    )

    assert migrated.frame_rate == old.update_rate


def test_session_config_is_timed_by_the_sensor():
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=8.0,
        sweep_rate=None,
        snr_evaluation_height_m=_height_at_z(0.0),
    )

    volume = _boresight_volume(0.5, 2.0)

    session_config = config.get_session_config(_LEVEL_MOUNT, volume)

    assert session_config.update_rate is None
    assert session_config.sensor_config.frame_rate == 8.0
    assert get_effective_frame_rate(session_config) == 8.0


def test_get_effective_frame_rate_falls_back_to_update_rate():
    """Sessions recorded before frame_rate was used were timed by update_rate."""
    session_config = a2.SessionConfig.default()
    session_config.sensor_config.frame_rate = None
    session_config.update_rate = 12.0

    assert get_effective_frame_rate(session_config) == 12.0


def test_get_effective_frame_rate_is_none_without_a_rate():
    session_config = a2.SessionConfig.default()
    session_config.sensor_config.frame_rate = None
    session_config.update_rate = None

    assert get_effective_frame_rate(session_config) is None


def test_sweep_rate_too_low_for_frame_rate_points_at_the_rates_only():
    """Raising frame_rate past what the set sweep_rate allows is the rates'
    problem, not the signal quality's or the volume's."""
    volume = _boresight_volume(0.5, 2.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.0,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        sweeps_per_frame=16,
        sweep_rate=140.0,
        snr_evaluation_height_m=_height_at_z(0.0),
    )
    results = config._collect_validation_results(_LEVEL_MOUNT, volume)

    errors = {(r.aspect, r.message) for r in results if isinstance(r, ValidationError)}
    message = (
        "Sweep rate too low for the frame rate. "
        "Increase the sweep rate or decrease the frame rate."
    )
    assert errors == {("frame_rate", message), ("sweep_rate", message)}
    assert not any(r.aspect in ("signal_quality_db", "y_bounds_m") for r in results)
    at_max_sweep_rate = attrs.evolve(config, sweep_rate=None)
    assert at_max_sweep_rate._collect_validation_results(_LEVEL_MOUNT, volume) == []


@pytest.mark.parametrize(
    "old",
    [
        _WallMountSessionAbstractionConfig_v1(
            signal_quality_db=27.5,
            profile=a2.Profile.PROFILE_5,
            update_rate=8.0,
            max_num_subsweeps=3,
            snr_evaluation_z_m=-0.5,
            sweep_rate=70.0,
        ),
        _WallMountSessionAbstractionConfig_v2(
            signal_quality_db=27.5,
            profile=a2.Profile.PROFILE_5,
            frame_rate=8.0,
            max_num_subsweeps=3,
            snr_evaluation_z_m=-0.5,
            sweep_rate=70.0,
        ),
    ],
    ids=["v1", "v2"],
)
def test_migration_measures_the_plane_from_the_installations_floor(old):
    """snr_evaluation_z_m was relative to the sensor, which the installation
    recorded alongside it mounts mount_height_m above the floor."""
    migrated = session_abstraction_config_timeline.migrate(
        old.to_json(), completer=lambda _: _LEVEL_MOUNT
    )

    assert migrated == WallMountSessionAbstractionConfig(
        signal_quality_db=27.5,
        profile=a2.Profile.PROFILE_5,
        frame_rate=8.0,
        max_num_subsweeps=3,
        snr_evaluation_height_m=1.0,
        sweep_rate=70.0,
    )
