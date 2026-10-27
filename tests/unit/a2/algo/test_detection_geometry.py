# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for SensorInstallation and DetectionVolume, and for the geometry
WallMountSessionAbstractionConfig derives from them."""

from __future__ import annotations

import itertools
import json
import math
import warnings

import h5py
import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationWarning,
)
from acconeer.exptool.a2.algo._detection_geometry import (
    DETECTION_VOLUME_DATASET_NAME,
    LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME,
    SENSOR_INSTALLATION_DATASET_NAME,
    DetectionVolume,
    SensorInstallation,
    load_detection_geometry,
    save_detection_geometry,
    split_legacy_detection_volume_config,
)
from acconeer.exptool.a2.algo._shared_config import (
    MAX_RANGE_M,
    WallMountSessionAbstractionConfig,
    _edge_crossing_xy,
    _in_volume,
    _required_range_m,
    room_z_bounds_m,
)
from acconeer.exptool.a2.algo._utils import BASE_STEP_LENGTH_M, get_measured_range
from acconeer.exptool.a2.algo.motion_detection import MotionDetectionConfig
from acconeer.exptool.a2.algo.nodes._heatmap_peak_nodes import ExclusionZone
from acconeer.exptool.a2.algo.nodes._spherical_to_cartesian_nodes import (
    RigidTransformNode,
    RotationMatrix,
    SphericalToCartesianNode,
)


_LEVEL_MOUNT = SensorInstallation(mount_height_m=1.5)

_ROTATIONS = [(0.0, 0.0, 0.0), (15.0, 0.0, -10.0), (-30.0, 25.0, 20.0), (45.0, -60.0, 35.0)]


def _make_volume(**overrides):
    kwargs = dict(x_bounds_m=(-4.0, 4.0), y_bounds_m=(1.0, 6.0))
    kwargs.update(overrides)
    return DetectionVolume(**kwargs)


def _corner_angle_reference(world_point, x_rot_deg, y_rot_deg, z_rot_deg):
    """Non-vectorized reference implementation of the world-to-sensor angle
    computation, independent of SensorInstallation's own implementation."""
    R = RotationMatrix(x_deg=x_rot_deg, y_deg=y_rot_deg, z_deg=z_rot_deg).matrix
    raw = R.T @ np.array(world_point, dtype=np.float64)
    az = math.degrees(math.atan2(raw[0], math.sqrt(raw[1] ** 2 + raw[2] ** 2)))
    el = math.degrees(math.atan2(raw[2], raw[1]))
    return az, el


# --- SensorInstallation -------------------------------------------------------


def test_installation_defaults_to_an_upside_down_level_mount():
    installation = SensorInstallation(mount_height_m=1.5)
    assert (installation.x_rotation, installation.y_rotation, installation.z_rotation) == (
        0.0,
        180.0,
        0.0,
    )


def test_installation_requires_a_mount_height():
    with pytest.raises(TypeError, match="mount_height_m"):
        SensorInstallation()  # type: ignore[call-arg]


def test_installation_rejects_negative_mount_height():
    with pytest.raises(ValueError):
        SensorInstallation(mount_height_m=-0.1)


@pytest.mark.parametrize("x_rot,y_rot,z_rot", _ROTATIONS)
def test_sensor_to_world_applies_the_mount_rotation(x_rot, y_rot, z_rot):
    installation = SensorInstallation(
        x_rotation=x_rot, y_rotation=y_rot, z_rotation=z_rot, mount_height_m=1.5
    )
    rotation_matrix = RotationMatrix(x_deg=x_rot, y_deg=y_rot, z_deg=z_rot).matrix
    points_sensor = np.array([[0.0, 1.0, 0.0], [1.0, 2.0, -0.5], [-3.0, 0.5, 2.0]])

    np.testing.assert_allclose(
        installation.sensor_to_world(points_sensor), points_sensor @ rotation_matrix.T
    )


@pytest.mark.parametrize("x_rot,y_rot,z_rot", _ROTATIONS)
def test_world_to_sensor_inverts_sensor_to_world(x_rot, y_rot, z_rot):
    installation = SensorInstallation(
        x_rotation=x_rot, y_rotation=y_rot, z_rotation=z_rot, mount_height_m=1.5
    )
    points_world = np.array([[0.0, 1.0, 0.0], [1.0, 2.0, -0.5], [-3.0, 0.5, 2.0]])

    np.testing.assert_allclose(
        installation.sensor_to_world(installation.world_to_sensor(points_world)),
        points_world,
        atol=1e-12,
    )


def test_sensor_and_world_share_their_origin():
    installation = SensorInstallation(x_rotation=-20.0, z_rotation=30.0, mount_height_m=1.5)
    np.testing.assert_array_equal(installation.sensor_to_world(np.zeros(3)), np.zeros(3))


@pytest.mark.parametrize("y_rot", [0.0, 180.0])
def test_supported_roll_validates_cleanly(y_rot):
    assert (
        SensorInstallation(y_rotation=y_rot, mount_height_m=1.5)._collect_validation_results()
        == []
    )


def test_unsupported_roll_is_a_warning():
    (result,) = SensorInstallation(
        y_rotation=45.0, mount_height_m=1.5
    )._collect_validation_results()
    assert isinstance(result, ValidationWarning)
    assert result.aspect == "y_rotation"


def test_validate_warns_on_unsupported_roll_instead_of_raising():
    with pytest.warns(UserWarning, match="y_rotation is 45.0°"):
        SensorInstallation(y_rotation=45.0, mount_height_m=1.5).validate()


@pytest.mark.parametrize("y_rot", [0.0, 180.0])
def test_validate_is_quiet_for_supported_roll(y_rot):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        SensorInstallation(y_rotation=y_rot, mount_height_m=1.5).validate()


def test_installation_json_round_trip():
    installation = SensorInstallation(
        x_rotation=3.0, y_rotation=180.0, z_rotation=-2.0, mount_height_m=2.2
    )
    assert SensorInstallation.from_json(installation.to_json()) == installation


# --- DetectionVolume fields ---------------------------------------------------


def test_volume_bounds_default_to_none():
    volume = DetectionVolume()
    assert volume.x_bounds_m is None
    assert volume.y_bounds_m is None
    assert volume.start_m is None
    assert volume.end_m is None


def test_angle_range_defaults_match_processor_defaults():
    volume = _make_volume()
    assert volume.az_angle_range == (-60.0, 60.0)
    assert volume.el_angle_range == (-30.0, 30.0)


def test_validators_reject_lo_ge_hi():
    with pytest.raises(ValueError):
        _make_volume(x_bounds_m=(4.0, 4.0))


def test_validators_reject_bounds_below_negative_max_range():
    with pytest.raises(ValueError):
        _make_volume(y_bounds_m=(-MAX_RANGE_M - 1.0, 0.0))


def test_validators_reject_bounds_above_max_range():
    with pytest.raises(ValueError):
        _make_volume(y_bounds_m=(0.0, MAX_RANGE_M + 1.0))


def test_validators_accept_bounds_at_max_range():
    _make_volume(x_bounds_m=(-MAX_RANGE_M, MAX_RANGE_M))


def test_validators_reject_az_angle_range_lo_ge_hi():
    with pytest.raises(ValueError):
        _make_volume(az_angle_range=(10.0, 10.0))


def test_validators_reject_el_angle_range_lo_ge_hi():
    with pytest.raises(ValueError):
        _make_volume(el_angle_range=(5.0, -5.0))


@pytest.mark.parametrize(
    "overrides",
    [
        dict(start_m=-0.1),
        dict(start_m=MAX_RANGE_M),
        dict(end_m=0.0),
        dict(end_m=MAX_RANGE_M + 0.1),
    ],
)
def test_validators_reject_range_limits_outside_reach(overrides):
    with pytest.raises(ValueError):
        _make_volume(**overrides)


def test_volume_json_round_trip_without_a_box():
    volume = DetectionVolume(
        start_m=0.3,
        end_m=5.0,
        az_angle_range=(-45.0, 50.0),
        el_angle_range=(-20.0, 25.0),
    )
    restored = DetectionVolume.from_json(volume.to_json())
    assert restored == volume
    assert restored.x_bounds_m is None


_ZONES = (
    ExclusionZone(center=(1.0, 2.0), radius_m=0.5),
    ExclusionZone(center=(-2.5, 4.0), radius_m=1.25),
)


def test_exclusion_zones_default_to_empty():
    assert _make_volume().exclusion_zones == ()


def test_exclusion_zones_to_dict_from_dict_round_trip():
    volume = _make_volume(exclusion_zones=_ZONES)
    restored = DetectionVolume.from_dict(volume.to_dict())
    assert restored == volume
    assert restored.exclusion_zones == _ZONES


def test_exclusion_zones_to_json_from_json_round_trip():
    volume = _make_volume(exclusion_zones=_ZONES)
    restored = DetectionVolume.from_json(volume.to_json())
    assert restored == volume
    assert restored.exclusion_zones == _ZONES


def test_from_dict_without_exclusion_zones_loads_empty():
    dict_repr = _make_volume().to_dict()
    del dict_repr["exclusion_zones"]
    assert DetectionVolume.from_dict(dict_repr).exclusion_zones == ()


def test_exclusion_zones_converter_normalizes_list_center():
    volume = _make_volume(exclusion_zones=[{"center": [1, 2], "radius_m": 0.5}])
    assert volume.exclusion_zones == (ExclusionZone(center=(1.0, 2.0), radius_m=0.5),)


def test_exclusion_zones_reject_non_positive_radius():
    with pytest.raises(ValueError):
        _make_volume(exclusion_zones=[{"center": (1.0, 2.0), "radius_m": 0.0}])


# --- DetectionVolume validation -----------------------------------------------


@pytest.mark.parametrize(
    "volume",
    [
        _make_volume(),
        # A box with the default height, the room's.
        DetectionVolume(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.0, 6.0)),
        DetectionVolume(end_m=5.0),
        DetectionVolume(start_m=0.5, end_m=5.0),
    ],
)
def test_volume_with_a_farthest_point_validates_cleanly(volume):
    assert volume._collect_validation_results() == []
    volume.validate()  # must not raise


@pytest.mark.parametrize(
    "volume",
    [
        DetectionVolume(),
        DetectionVolume(start_m=1.0),
    ],
)
def test_volume_without_a_farthest_point_is_an_error(volume):
    with pytest.raises(ValidationError) as exc_info:
        volume.validate()
    assert exc_info.value.aspect == "end_m"


@pytest.mark.parametrize(
    "bounds,missing",
    [
        (dict(x_bounds_m=(-4.0, 4.0)), ["y_bounds_m"]),
        (dict(y_bounds_m=(0.0, 6.0)), ["x_bounds_m"]),
    ],
)
def test_box_bounds_x_and_y_together(bounds, missing):
    # With or without end_m: a partial box is the error, not the missing end.
    for end_m in (None, 5.0):
        errors = DetectionVolume(**bounds, end_m=end_m)._collect_validation_results()
        assert [error.aspect for error in errors] == missing


@pytest.mark.parametrize("z_bounds_m", [None, [-1.0, 0.5]])
def test_volume_loads_with_a_stored_box_height(z_bounds_m):
    # The box's height was settable; recordings still hold it.
    stored = {**_make_volume().to_dict(), "z_bounds_m": z_bounds_m}
    assert DetectionVolume.from_json(json.dumps(stored)) == _make_volume()


def test_start_at_or_beyond_end_is_an_error():
    with pytest.raises(ValidationError) as exc_info:
        DetectionVolume(start_m=3.0, end_m=3.0).validate()
    assert exc_info.value.aspect == "start_m"


@pytest.mark.parametrize("name", ["az_angle_range", "el_angle_range"])
def test_angle_range_must_lie_inside_hemisphere(name):
    errors = _make_volume(**{name: (-90.0, 10.0)})._collect_validation_results()
    assert [error.aspect for error in errors] == [name]


# --- room height ------------------------------------------------------------


@pytest.mark.parametrize("mount_height_m,z_bounds_m", [(2.0, (-2.0, 0.5)), (1.0, (-1.0, 1.5))])
def test_room_runs_from_the_floor_up_a_room_height(mount_height_m, z_bounds_m):
    assert room_z_bounds_m(SensorInstallation(mount_height_m=mount_height_m)) == z_bounds_m


# --- required range, derived in WallMountSessionAbstractionConfig ------------


@pytest.mark.parametrize("x_bounds_m", [(-7.0, 1.0), (-1.0, 7.0)])
def test_box_end_picks_larger_magnitude_bound_per_axis(x_bounds_m):
    volume = _make_volume(x_bounds_m=x_bounds_m, y_bounds_m=(1.0, 2.0))
    _, end_m = _required_range_m(_LEVEL_MOUNT, volume)
    assert end_m == pytest.approx(math.sqrt(7.0**2 + 2.0**2 + 1.5**2))


def test_box_beyond_max_range_is_an_error():
    volume = _make_volume(x_bounds_m=(-9.0, 9.0), y_bounds_m=(-9.0, 9.0))
    with pytest.raises(ValidationError) as exc_info:
        _required_range_m(_LEVEL_MOUNT, volume)
    assert exc_info.value.aspect == "end_m"


def test_end_m_cuts_a_box_beyond_max_range():
    volume = _make_volume(x_bounds_m=(-9.0, 9.0), y_bounds_m=(-9.0, 9.0), end_m=6.0)
    assert _required_range_m(_LEVEL_MOUNT, volume) == (0.0, 6.0)


def test_box_start_is_zero_when_sensor_is_inside_the_box():
    volume = _make_volume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(-1.0, 5.0))
    start_m, _ = _required_range_m(_LEVEL_MOUNT, volume)
    assert start_m == 0.0


def test_box_start_reduces_to_y_bound_when_x_and_z_straddle_sensor():
    volume = _make_volume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(2.0, 5.0))
    start_m, _ = _required_range_m(_LEVEL_MOUNT, volume)
    assert start_m == pytest.approx(2.0)


def test_box_start_is_not_driven_by_y_alone():
    # x is offset to one side too (doesn't straddle 0), so the true nearest
    # point pulls in the x-distance as well -- it's not just y_bounds_m[0].
    volume = _make_volume(x_bounds_m=(1.0, 4.0), y_bounds_m=(2.0, 5.0))
    start_m, _ = _required_range_m(_LEVEL_MOUNT, volume)
    assert start_m == pytest.approx(math.sqrt(1.0**2 + 2.0**2))


def test_box_start_picks_nearer_bound_when_axis_is_entirely_negative():
    # A box entirely behind the sensor along y: nearest point uses the
    # bound closer to 0, i.e. -2.0, not the farther one, -5.0.
    volume = _make_volume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(-5.0, -2.0))
    start_m, _ = _required_range_m(_LEVEL_MOUNT, volume)
    assert start_m == pytest.approx(2.0)


@pytest.mark.parametrize(
    "start_m,end_m,expected",
    [
        (None, None, (2.0, math.sqrt(3.0**2 + 5.0**2 + 1.5**2))),
        (3.0, 4.0, (3.0, 4.0)),  # the range limits are stricter
        (1.0, 9.0, (2.0, math.sqrt(3.0**2 + 5.0**2 + 1.5**2))),  # the box is stricter
    ],
)
def test_box_and_range_limits_combine_to_the_stricter(start_m, end_m, expected):
    volume = _make_volume(
        x_bounds_m=(-3.0, 3.0),
        y_bounds_m=(2.0, 5.0),
        start_m=start_m,
        end_m=end_m,
    )
    assert _required_range_m(_LEVEL_MOUNT, volume) == pytest.approx(expected)


def test_box_reaches_the_floor():
    volume = DetectionVolume(x_bounds_m=(-3.0, 3.0), y_bounds_m=(2.0, 5.0))
    _, end_m = _required_range_m(SensorInstallation(mount_height_m=2.0), volume)
    assert end_m == pytest.approx(math.sqrt(3.0**2 + 5.0**2 + 2.0**2))


def test_range_limits_alone_set_the_range():
    assert _required_range_m(_LEVEL_MOUNT, DetectionVolume(end_m=5.0)) == (0.0, 5.0)
    assert _required_range_m(_LEVEL_MOUNT, DetectionVolume(start_m=0.5, end_m=5.0)) == (0.5, 5.0)


def test_session_config_without_a_box_measures_the_range_limits():
    volume = DetectionVolume(start_m=1.0, end_m=5.0)
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=1.0,
        snr_evaluation_height_m=0.7,
        sweep_rate=None,
    )

    session_config = config.get_session_config(_LEVEL_MOUNT, volume)

    # The grid samples the range to within a step at either end.
    step_m = session_config.sensor_config.subsweeps[0].step_length * BASE_STEP_LENGTH_M
    start_m, end_m = get_measured_range(config=session_config)
    assert start_m == pytest.approx(1.0, abs=step_m)
    assert end_m == pytest.approx(5.0, abs=step_m)
    assert config._collect_validation_results(_LEVEL_MOUNT, volume) == []


@pytest.mark.parametrize(
    "overrides,aspect",
    [
        # start_m beyond the box's farthest corner.
        (dict(start_m=9.0), "start_m"),
        # end_m short of the box's nearest point; start_m is not even set.
        (dict(y_bounds_m=(5.0, 6.0), end_m=3.0), "end_m"),
    ],
)
def test_range_limits_outside_the_box_blame_the_limit_that_empties_it(overrides, aspect):
    volume = _make_volume(**overrides)
    with pytest.raises(ValidationError) as exc_info:
        _required_range_m(_LEVEL_MOUNT, volume)
    assert exc_info.value.aspect == aspect


def test_range_of_an_invalid_volume_is_an_error():
    with pytest.raises(ValidationError) as exc_info:
        _required_range_m(_LEVEL_MOUNT, DetectionVolume())
    assert exc_info.value.aspect == "end_m"


# --- inside the volume --------------------------------------------------------


def _inside(volume, points_world, az_deg=0.0, el_deg=0.0):
    points_world = np.asarray(points_world, dtype=np.float64)
    angles = np.zeros(points_world.shape[:-1])
    return _in_volume(volume, points_world, angles + az_deg, angles + el_deg)


def test_in_volume_includes_the_box_bounds():
    volume = _make_volume(x_bounds_m=(-1.0, 1.0), y_bounds_m=(2.0, 3.0))
    points = [
        [-1.0, 2.0, 0.0],
        [1.0, 3.0, 0.0],
        [0.0, 2.5, 0.0],
        [0.0, 3.01, 0.0],
        [-1.01, 2.5, 0.0],
        [0.0, 1.99, 0.0],
    ]
    np.testing.assert_array_equal(_inside(volume, points), [True, True, True, False, False, False])


def test_in_volume_ignores_the_height():
    # The box bounds only x and y.
    volume = _make_volume(x_bounds_m=(-1.0, 1.0), y_bounds_m=(2.0, 3.0))
    np.testing.assert_array_equal(
        _inside(volume, [[0.0, 2.5, -9.0], [0.0, 2.5, 9.0]]), [True, True]
    )


def test_in_volume_without_a_box_is_limited_by_range_alone():
    volume = DetectionVolume(end_m=9.0)
    np.testing.assert_array_equal(
        _inside(volume, [[-5.0, 7.0, 0.0], [5.0, -3.0, 4.0], [0.0, 9.5, 0.0]]),
        [True, True, False],
    )


def test_in_volume_includes_the_range_limits():
    volume = DetectionVolume(start_m=1.0, end_m=2.0)
    np.testing.assert_array_equal(
        _inside(volume, [[0.0, 0.99, 0.0], [0.0, 1.0, 0.0], [0.0, 2.0, 0.0], [0.0, 2.01, 0.0]]),
        [False, True, True, False],
    )


def test_in_volume_includes_the_angle_bounds():
    volume = _make_volume(az_angle_range=(-50.0, 20.0), el_angle_range=(-30.0, 10.0))
    points = np.tile([0.0, 2.0, 0.0], (7, 1))
    az_deg = np.array([-50.0, 20.0, 0.0, -50.1, 20.1, 0.0, 0.0])
    el_deg = np.array([-30.0, 10.0, 0.0, 0.0, 0.0, -30.1, 10.1])
    np.testing.assert_array_equal(
        _in_volume(volume, points, az_deg, el_deg),
        [True, True, True, False, False, False, False],
    )


def test_volume_without_a_box_has_no_edge_crossings():
    volume = DetectionVolume(end_m=9.0)
    _, _, exists = _edge_crossing_xy(volume, np.array([1.0, 3.0, 5.0]))
    assert exists.shape == (3, 8)
    assert not exists.any()


# --- production pipeline ------------------------------------------------------


@pytest.mark.parametrize("x_rot,y_rot,z_rot", _ROTATIONS)
def test_inverse_rotation_round_trips_through_production_pipeline(x_rot, y_rot, z_rot):
    """Feed each corner's own reported sensor-frame angle back through the
    nodes the processors use (SphericalToCartesianNode, then a
    RigidTransformNode with the installation's mount rotation) and confirm it
    lands exactly back on that corner -- including cases with nonzero roll
    (y_rot)."""
    x_bounds, y_bounds, z_bounds = (-4.0, 4.0), (1.0, 6.0), (-1.5, 1.0)
    spherical_to_cartesian = SphericalToCartesianNode()
    installation = SensorInstallation(
        x_rotation=x_rot, y_rotation=y_rot, z_rotation=z_rot, mount_height_m=1.5
    )
    sensor_to_world = RigidTransformNode(installation.mount_rotation)

    for corner in itertools.product(x_bounds, y_bounds, z_bounds):
        corner_arr = np.array(corner, dtype=np.float64)
        distance_m = float(np.linalg.norm(corner_arr))
        az, el = _corner_angle_reference(corner_arr, x_rot, y_rot, z_rot)

        sensor_point = spherical_to_cartesian.execute(np.array([distance_m, az, el]))
        world_point = sensor_to_world.execute(sensor_point)

        np.testing.assert_allclose(world_point, corner_arr, atol=1e-9)


# --- legacy recordings and h5 -------------------------------------------------

_LEGACY_JSON = json.dumps(
    {
        "x_bounds_m": [-4.0, 4.0],
        "y_bounds_m": [0.0, 6.0],
        "z_bounds_m": [-1.5, 1.0],
        "x_rotation": -20.0,
        "y_rotation": 180.0,
        "z_rotation": 30.0,
        "az_angle_range": [-45.0, 50.0],
        "el_angle_range": [-20.0, 25.0],
    }
)


def test_split_legacy_moves_rotations_to_the_installation():
    installation, volume = split_legacy_detection_volume_config(_LEGACY_JSON)

    assert installation == SensorInstallation(
        x_rotation=-20.0, y_rotation=180.0, z_rotation=30.0, mount_height_m=1.5
    )
    assert volume == DetectionVolume(
        x_bounds_m=(-4.0, 4.0),
        y_bounds_m=(0.0, 6.0),
        az_angle_range=(-45.0, 50.0),
        el_angle_range=(-20.0, 25.0),
    )


def test_legacy_json_loads_as_either_part():
    # What the old Detection Volume editor saved; each new editor takes its part.
    expected_installation, expected_volume = split_legacy_detection_volume_config(_LEGACY_JSON)

    assert SensorInstallation.from_json(_LEGACY_JSON) == expected_installation
    assert DetectionVolume.from_json(_LEGACY_JSON) == expected_volume
    assert expected_installation.mount_height_m == 1.5


def test_split_legacy_without_optional_fields_takes_defaults_and_floor_at_box_bottom():
    legacy = {"x_bounds_m": [-1.0, 1.0], "y_bounds_m": [0.5, 3.0], "z_bounds_m": [-1.0, 0.5]}

    installation, volume = split_legacy_detection_volume_config(json.dumps(legacy))

    assert installation == SensorInstallation(mount_height_m=1.0)
    assert volume == DetectionVolume(x_bounds_m=(-1.0, 1.0), y_bounds_m=(0.5, 3.0))


def test_save_and_load_round_trip(tmp_path):
    installation = SensorInstallation(x_rotation=-10.0, mount_height_m=2.0)
    volume = DetectionVolume(start_m=0.3, end_m=5.0)

    with h5py.File(tmp_path / "geometry.h5", "w") as file:
        save_detection_geometry(file, installation, volume)
        assert set(file) == {SENSOR_INSTALLATION_DATASET_NAME, DETECTION_VOLUME_DATASET_NAME}
        assert load_detection_geometry(file) == (installation, volume)


def test_load_falls_back_to_the_legacy_dataset(tmp_path):
    with h5py.File(tmp_path / "legacy.h5", "w") as file:
        file.create_dataset(LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME, data=_LEGACY_JSON)
        assert load_detection_geometry(file) == split_legacy_detection_volume_config(_LEGACY_JSON)


def test_load_prefers_the_new_datasets_over_the_legacy_one(tmp_path):
    installation, volume = (
        SensorInstallation(z_rotation=5.0, mount_height_m=1.5),
        DetectionVolume(end_m=4.0),
    )

    with h5py.File(tmp_path / "both.h5", "w") as file:
        file.create_dataset(LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME, data=_LEGACY_JSON)
        save_detection_geometry(file, installation, volume)
        assert load_detection_geometry(file) == (installation, volume)


def test_load_is_none_without_geometry(tmp_path):
    with h5py.File(tmp_path / "empty.h5", "w") as file:
        assert load_detection_geometry(file) is None


# --- Processor-config overrides against the volume ---

_PROCESSOR_CONFIG_CLASSES = [
    MotionDetectionConfig,
]


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_effective_bounds_are_none_without_offset(config_cls):
    config = config_cls(antenna_array=a2.AntennaArray.AP212)
    volume = _make_volume()
    assert config.effective_x_bounds_m(volume) is None
    assert config.effective_y_bounds_m(volume) is None
    assert config.effective_z_bounds_m(_LEVEL_MOUNT, volume) is None


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_effective_bounds_add_offset_to_volume_bounds(config_cls):
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_x_bound_offset_m=(-1.0, 1.0),
        detection_volume_y_bound_offset_m=(0.5, -0.5),
        detection_volume_z_bound_offset_m=(0.0, 0.0),
    )
    volume = _make_volume(x_bounds_m=(-2.0, 2.0), y_bounds_m=(1.0, 6.0))
    assert config.effective_x_bounds_m(volume) == (-3.0, 3.0)
    assert config.effective_y_bounds_m(volume) == (1.5, 5.5)
    assert config.effective_z_bounds_m(_LEVEL_MOUNT, volume) == (-1.5, 1.0)


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_effective_bounds_are_none_without_a_box(config_cls):
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_x_bound_offset_m=(0.0, 0.0),
        detection_volume_y_bound_offset_m=(0.0, 0.0),
        detection_volume_z_bound_offset_m=(0.0, 0.0),
    )
    volume = DetectionVolume(end_m=5.0)
    assert config.effective_x_bounds_m(volume) is None
    assert config.effective_y_bounds_m(volume) is None
    assert config.effective_z_bounds_m(_LEVEL_MOUNT, volume) is None


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_effective_z_bounds_offset_the_box_height(config_cls):
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212, detection_volume_z_bound_offset_m=(0.5, -0.5)
    )
    volume = DetectionVolume(x_bounds_m=(-2.0, 2.0), y_bounds_m=(1.0, 6.0))
    assert config.effective_z_bounds_m(SensorInstallation(mount_height_m=2.0), volume) == (
        -1.5,
        0.0,
    )


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_effective_angle_ranges_fall_back_to_volume(config_cls):
    config = config_cls(antenna_array=a2.AntennaArray.AP212)
    volume = _make_volume(az_angle_range=(-45.0, 50.0), el_angle_range=(-20.0, 25.0))
    assert config.az_angle_range is None
    assert config.el_angle_range is None
    assert config.effective_az_angle_range(volume) == (-45.0, 50.0)
    assert config.effective_el_angle_range(volume) == (-20.0, 25.0)


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_effective_angle_ranges_prefer_processor_override(config_cls):
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        az_angle_range=(-30.0, 30.0),
        el_angle_range=(-10.0, 10.0),
    )
    volume = _make_volume(az_angle_range=(-45.0, 50.0), el_angle_range=(-20.0, 25.0))
    assert config.effective_az_angle_range(volume) == (-30.0, 30.0)
    assert config.effective_el_angle_range(volume) == (-10.0, 10.0)


# --- detection-volume offset validation -------------------------------------
#
# The offsets are per-side offsets added to the volume's bounds, not ranges in
# their own right: ``(0.0, 0.0)`` means "leave this axis as the volume has it"
# (what every shipped preset uses) and ``(lo > hi)`` narrows the box from both
# sides. Only the *resulting* bound has to be non-empty, which cannot be judged
# from the offset pair alone -- it depends on the volume being offset.


def _session_for(volume):
    return WallMountSessionAbstractionConfig(
        signal_quality_db=20.5,
        profile=a2.Profile.PROFILE_3,
        frame_rate=10.0,
        snr_evaluation_height_m=0.7,
        sweep_rate=None,
    ).get_session_config(_LEVEL_MOUNT, volume)


def _offset_errors(config, volume):
    session = _session_for(volume)
    return [
        r
        for r in config._collect_validation_results(session, _LEVEL_MOUNT, volume)
        if isinstance(r, ValidationError) and r.aspect.endswith("_bound_offset_m")
    ]


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_zero_offsets_are_valid(config_cls):
    # Regression: every shipped preset leaves these at (0.0, 0.0), which a
    # naive ``lo < hi`` range check rejects -- making the default config fail
    # its own validation and, on replay, silently fall back to the default.
    volume = _make_volume()
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_x_bound_offset_m=(0.0, 0.0),
        detection_volume_y_bound_offset_m=(0.0, 0.0),
        detection_volume_z_bound_offset_m=(0.0, 0.0),
    )

    assert _offset_errors(config, volume) == []


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_offsets_narrowing_the_volume_from_both_sides_are_valid(config_cls):
    # (0.5, -0.5) on y_bounds_m=(1.0, 6.0) narrows it to (1.5, 5.5) -- an
    # unordered offset pair that is perfectly meaningful.
    volume = _make_volume()
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_y_bound_offset_m=(0.5, -0.5),
    )

    assert config.effective_y_bounds_m(volume) == (1.5, 5.5)
    assert _offset_errors(config, volume) == []


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_offsets_that_collapse_the_bound_are_rejected(config_cls):
    # x_bounds_m=(-4.0, 4.0) narrowed by 5 m per side inverts to (1.0, -1.0).
    volume = _make_volume()
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_x_bound_offset_m=(5.0, -5.0),
    )

    errors = _offset_errors(config, volume)

    assert [e.aspect for e in errors] == ["detection_volume_x_bound_offset_m"]
    assert "empty bound" in errors[0].message


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_offsets_that_exactly_close_the_bound_are_rejected(config_cls):
    # Degenerate rather than inverted: (-4.0, 4.0) -> (0.0, 0.0), zero width.
    volume = _make_volume()
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_x_bound_offset_m=(4.0, -4.0),
    )

    errors = _offset_errors(config, volume)

    assert [e.aspect for e in errors] == ["detection_volume_x_bound_offset_m"]
    assert "empty bound" in errors[0].message


@pytest.mark.parametrize("config_cls", _PROCESSOR_CONFIG_CLASSES)
def test_offsets_pushing_past_the_sensor_reach_are_still_rejected(config_cls):
    # The reach check must survive the fix: a non-empty bound that lands
    # outside +-MAX_RANGE_M is still an error, and a distinct one.
    volume = _make_volume()
    config = config_cls(
        antenna_array=a2.AntennaArray.AP212,
        detection_volume_x_bound_offset_m=(-MAX_RANGE_M, 0.0),
    )

    errors = _offset_errors(config, volume)

    assert [e.aspect for e in errors] == ["detection_volume_x_bound_offset_m"]
    assert "empty bound" not in errors[0].message
    assert str(MAX_RANGE_M) in errors[0].message
