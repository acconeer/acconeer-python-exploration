# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for the public symbols of ``_spherical_to_cartesian_nodes``.

Four public symbols are tested:

* ``RotationMatrix(x_deg, y_deg, z_deg)`` — composes
  ``Rz @ Rx @ Ry`` from per-axis right-handed rotations. The matrix is
  available via the ``.matrix`` attribute; ``apply``/``apply_inverse``
  rotate points by ``R``/``R.T``.
* ``build_mount_rotation_matrix(x_rotation=0.0, y_rotation=0.0,
  z_rotation=0.0)`` — returns a ``RotationMatrix`` for
  ``Rz(z_rotation) @ Rx(x_rotation) @ Ry(y_rotation)``.
* ``RigidTransformNode(rotation, translation)`` — applies
  ``p' = R @ p + t`` to a batch of 3D points.
* ``SphericalToCartesianNode()`` — projects ``(d, az, el)`` to
  sensor-frame Cartesian ``(x, y, z)`` with boresight along ``+y``
  (datasheet convention, eqs. 16.2–16.4).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool.a2.algo.nodes._spherical_to_cartesian_nodes import (
    RigidTransformNode,
    RotationMatrix,
    SphericalToCartesianNode,
    build_mount_rotation_matrix,
)


# --- Constants ---

_NUM_SAMPLES = 32
_RTOL = 1e-12
_ATOL = 1e-15


# --- Reference helpers ---


def _ref_rx(deg: float) -> npt.NDArray[np.float64]:
    """Right-handed rotation around the x-axis."""
    r = np.deg2rad(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, c, -s],
            [0.0, s, c],
        ]
    )


def _ref_ry(deg: float) -> npt.NDArray[np.float64]:
    """Right-handed rotation around the y-axis."""
    r = np.deg2rad(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array(
        [
            [c, 0.0, s],
            [0.0, 1.0, 0.0],
            [-s, 0.0, c],
        ]
    )


def _ref_rz(deg: float) -> npt.NDArray[np.float64]:
    """Right-handed rotation around the z-axis."""
    r = np.deg2rad(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )


def _random_points(rng: np.random.Generator, shape: tuple[int, ...]) -> npt.NDArray[np.float64]:
    return rng.uniform(-5.0, 5.0, size=shape)


def _random_spherical(rng: np.random.Generator, n: int) -> npt.NDArray[np.float64]:
    """Random ``(N, 3)`` array with columns ``(d, az_deg, el_deg)`` over realistic ranges."""
    d = rng.uniform(0.1, 5.0, size=n)
    az = rng.uniform(-180.0, 180.0, size=n)
    el = rng.uniform(-89.0, 89.0, size=n)  # avoid the poles
    return np.stack([d, az, el], axis=-1)


# --- RotationMatrix ---


def test_rotation_matrix_defaults_are_identity() -> None:
    """All-zero rotation must yield the identity matrix."""
    np.testing.assert_allclose(RotationMatrix().matrix, np.eye(3), rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize("deg", [-180.0, -45.0, 0.0, 30.0, 90.0, 180.0])
def test_rotation_matrix_pure_x_matches_reference(deg: float) -> None:
    """``RotationMatrix(x_deg=θ)`` equals an independent ``Rx(θ)``."""
    np.testing.assert_allclose(
        RotationMatrix(x_deg=deg).matrix, _ref_rx(deg), rtol=_RTOL, atol=_ATOL
    )


@pytest.mark.parametrize("deg", [-180.0, -45.0, 0.0, 30.0, 90.0, 180.0])
def test_rotation_matrix_pure_y_matches_reference(deg: float) -> None:
    """``RotationMatrix(y_deg=θ)`` equals an independent ``Ry(θ)``."""
    np.testing.assert_allclose(
        RotationMatrix(y_deg=deg).matrix, _ref_ry(deg), rtol=_RTOL, atol=_ATOL
    )


@pytest.mark.parametrize("deg", [-180.0, -45.0, 0.0, 30.0, 90.0, 180.0])
def test_rotation_matrix_pure_z_matches_reference(deg: float) -> None:
    """``RotationMatrix(z_deg=θ)`` equals an independent ``Rz(θ)``."""
    np.testing.assert_allclose(
        RotationMatrix(z_deg=deg).matrix, _ref_rz(deg), rtol=_RTOL, atol=_ATOL
    )


@pytest.mark.parametrize(
    "x_deg,y_deg,z_deg",
    [
        (10.0, 20.0, 30.0),
        (-45.0, 60.0, -90.0),
        (90.0, 45.0, 45.0),
        (180.0, 0.0, 90.0),
    ],
)
def test_rotation_matrix_composition_order(x_deg: float, y_deg: float, z_deg: float) -> None:
    """Composition order is ``Rz @ Rx @ Ry`` — verified by re-deriving the product."""
    expected = _ref_rz(z_deg) @ _ref_rx(x_deg) @ _ref_ry(y_deg)
    np.testing.assert_allclose(
        RotationMatrix(x_deg=x_deg, y_deg=y_deg, z_deg=z_deg).matrix,
        expected,
        rtol=_RTOL,
        atol=_ATOL,
    )


@pytest.mark.parametrize(
    "x_deg,y_deg,z_deg",
    [
        (0.0, 0.0, 0.0),
        (35.0, -50.0, 80.0),
        (-120.0, 60.0, 145.0),
    ],
)
def test_rotation_matrix_is_orthogonal(x_deg: float, y_deg: float, z_deg: float) -> None:
    """A valid rotation must satisfy ``R R^T = I`` and ``det(R) = +1``."""
    R = RotationMatrix(x_deg=x_deg, y_deg=y_deg, z_deg=z_deg).matrix
    np.testing.assert_allclose(R @ R.T, np.eye(3), rtol=_RTOL, atol=_ATOL)
    assert np.linalg.det(R) == pytest.approx(1.0, rel=_RTOL, abs=_ATOL)


def test_rotation_matrix_axis_handedness() -> None:
    """Hand-checked 90° rotations:
    ``Rx(90)`` maps +y → +z; ``Ry(90)`` maps +z → +x; ``Rz(90)`` maps +x → +y."""
    rx = RotationMatrix(x_deg=90.0).matrix
    ry = RotationMatrix(y_deg=90.0).matrix
    rz = RotationMatrix(z_deg=90.0).matrix
    np.testing.assert_allclose(rx @ [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], rtol=_RTOL, atol=_ATOL)
    np.testing.assert_allclose(ry @ [0.0, 0.0, 1.0], [1.0, 0.0, 0.0], rtol=_RTOL, atol=_ATOL)
    np.testing.assert_allclose(rz @ [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize("shape", [(3,), (_NUM_SAMPLES, 3), (4, 5, 3)])
def test_rotation_matrix_apply_matches_matrix_product(shape: tuple[int, ...]) -> None:
    """``apply`` is ``R @ p`` and ``apply_inverse`` is ``R.T @ p`` for every
    point along the last axis, for a single vector and for batches."""
    rng = np.random.default_rng(0)
    rotation = RotationMatrix(x_deg=15.0, y_deg=-25.0, z_deg=40.0)
    R = rotation.matrix
    points = _random_points(rng, shape)
    flat = points.reshape(-1, 3)

    expected_apply = np.array([R @ p for p in flat]).reshape(shape)
    expected_inverse = np.array([R.T @ p for p in flat]).reshape(shape)

    np.testing.assert_allclose(rotation.apply(points), expected_apply, rtol=_RTOL, atol=1e-12)
    np.testing.assert_allclose(
        rotation.apply_inverse(points), expected_inverse, rtol=_RTOL, atol=1e-12
    )
    np.testing.assert_allclose(
        rotation.apply_inverse(rotation.apply(points)), points, rtol=_RTOL, atol=1e-12
    )


# --- build_mount_rotation_matrix ---


def test_build_mount_rotation_matrix_zero_is_identity() -> None:
    """All-default args yield the identity matrix."""
    np.testing.assert_allclose(
        build_mount_rotation_matrix().matrix, np.eye(3), rtol=_RTOL, atol=_ATOL
    )


@pytest.mark.parametrize("z_deg", [-90.0, -30.0, 0.0, 45.0, 180.0])
def test_build_mount_rotation_matrix_pure_z_matches_rz(z_deg: float) -> None:
    """With x=y=0 the mount rotation is ``Rz(z_rotation)``."""
    np.testing.assert_allclose(
        build_mount_rotation_matrix(z_rotation=z_deg).matrix,
        _ref_rz(z_deg),
        rtol=_RTOL,
        atol=_ATOL,
    )


@pytest.mark.parametrize("x_deg", [-60.0, -15.0, 0.0, 30.0, 80.0])
def test_build_mount_rotation_matrix_pure_x_matches_rx(x_deg: float) -> None:
    """With y=z=0 the mount rotation is ``Rx(x_rotation)`` — tilts +y toward +z."""
    np.testing.assert_allclose(
        build_mount_rotation_matrix(x_rotation=x_deg).matrix,
        _ref_rx(x_deg),
        rtol=_RTOL,
        atol=_ATOL,
    )


@pytest.mark.parametrize("z_deg", [-90.0, 0.0, 45.0])
@pytest.mark.parametrize("x_deg", [-45.0, 0.0, 30.0])
@pytest.mark.parametrize("y_deg", [-90.0, 0.0, 60.0])
def test_build_mount_rotation_matrix_matches_underlying(
    x_deg: float, y_deg: float, z_deg: float
) -> None:
    """``build_mount_rotation_matrix(x, y, z) ==
    RotationMatrix(x_deg=x, y_deg=y, z_deg=z)``."""
    np.testing.assert_allclose(
        build_mount_rotation_matrix(x_deg, y_deg, z_deg).matrix,
        RotationMatrix(x_deg=x_deg, y_deg=y_deg, z_deg=z_deg).matrix,
        rtol=_RTOL,
        atol=_ATOL,
    )


def test_build_mount_rotation_matrix_z_rotation_defaults_to_zero() -> None:
    """Omitting ``z_rotation`` matches passing ``0.0`` explicitly."""
    for x_deg, y_deg in [(-45.0, 20.0), (0.0, 0.0), (60.0, -30.0)]:
        np.testing.assert_allclose(
            build_mount_rotation_matrix(x_deg, y_deg).matrix,
            build_mount_rotation_matrix(x_deg, y_deg, 0.0).matrix,
            rtol=_RTOL,
            atol=_ATOL,
        )


def test_build_mount_rotation_matrix_z_only_rotates_y_to_negative_x() -> None:
    """``(x=0, y=0, z=90)`` maps boresight +y to -x — standard right-handed
    rotation about z, the opposite direction from the spherical ``+az → +x``
    convention (the two are intentionally independent; see
    :func:`build_mount_rotation_matrix`'s docstring)."""
    R = build_mount_rotation_matrix(z_rotation=90.0).matrix
    np.testing.assert_allclose(R @ [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], rtol=_RTOL, atol=_ATOL)


def test_build_mount_rotation_matrix_x_only_tilts_y_to_z() -> None:
    """``(x=90, y=0, z=0)`` maps boresight +y to +z."""
    R = build_mount_rotation_matrix(x_rotation=90.0).matrix
    np.testing.assert_allclose(R @ [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], rtol=_RTOL, atol=_ATOL)


def test_build_mount_rotation_matrix_positive_x_pushes_boresight_above_xy_plane() -> None:
    """Sign convention behavioral pin: a sensor boresight (sensor-frame +y) projected
    through a mount rotation with a *positive* ``x_rotation`` must land with a positive
    z-component in world frame.

    This matches the spherical-coordinate convention used by
    :class:`SphericalToCartesianNode` where +el → +z (``z = d * cos(az) * sin(el)``),
    so a positive ``x_rotation`` semantically means "the sensor is tilted
    upward". The matrix-equality tests above don't catch a future sign flip as
    legibly as this end-to-end assertion does.
    """
    R = build_mount_rotation_matrix(x_rotation=10.0).matrix
    boresight_world = R @ np.array([0.0, 1.0, 0.0])
    assert boresight_world[2] > 0.0, (
        f"x_rotation=+10° must push boresight above the x-y plane; got z={boresight_world[2]}"
    )
    # Pin the exact value to catch numerical / convention regressions.
    np.testing.assert_allclose(
        boresight_world,
        [0.0, np.cos(np.deg2rad(10.0)), np.sin(np.deg2rad(10.0))],
        rtol=_RTOL,
        atol=_ATOL,
    )


@pytest.mark.parametrize("y_deg", [-170.0, -90.0, -10.0, 45.0, 90.0, 175.0])
def test_build_mount_rotation_matrix_roll_alone_leaves_boresight_unchanged(
    y_deg: float,
) -> None:
    """With x=0 and z=0, the boresight (+y) already lies exactly on the
    roll axis, so rolling around it — for any angle — leaves it unchanged.
    """
    R = build_mount_rotation_matrix(y_rotation=y_deg).matrix
    np.testing.assert_allclose(R @ [0.0, 1.0, 0.0], [0.0, 1.0, 0.0], rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize("z_deg", [-90.0, 0.0, 45.0])
@pytest.mark.parametrize("x_deg", [-45.0, 0.0, 30.0])
@pytest.mark.parametrize("y_deg", [-170.0, -90.0, -10.0, 45.0, 90.0, 175.0])
def test_build_mount_rotation_matrix_roll_never_perturbs_boresight(
    x_deg: float, y_deg: float, z_deg: float
) -> None:
    """Roll is applied first (innermost), before elevation/azimuth aim the
    boresight in the room-fixed frame, so it can never change where the
    boresight points — for any x/z, not just x=z=0. This matches the
    physical definition of roll (a twist around your own forward axis)."""
    without_roll = build_mount_rotation_matrix(x_deg, 0.0, z_deg).matrix @ [0.0, 1.0, 0.0]
    with_roll = build_mount_rotation_matrix(x_deg, y_deg, z_deg).matrix @ [0.0, 1.0, 0.0]
    np.testing.assert_allclose(with_roll, without_roll, rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize(("y_deg", "el_sign"), [(0.0, 1.0), (180.0, -1.0)])
@pytest.mark.parametrize("x_deg", [-40.0, 10.0, 30.0])
def test_build_mount_rotation_matrix_tilt_is_room_up_and_flips_sensor_elevation(
    x_deg: float, y_deg: float, el_sign: float
) -> None:
    """Positive tilt turns the boresight up in the room for any roll. In the
    rolled sensor's own frame that is positive elevation without roll and
    negative elevation with ``y_rotation=180``."""
    roll_only = build_mount_rotation_matrix(y_rotation=y_deg).matrix
    boresight = build_mount_rotation_matrix(x_deg, y_deg).matrix @ [0.0, 1.0, 0.0]
    np.testing.assert_allclose(boresight[2], np.sin(np.deg2rad(x_deg)), rtol=_RTOL, atol=_ATOL)

    _, y, z = roll_only.T @ boresight
    np.testing.assert_allclose(
        np.rad2deg(np.arctan2(z, y)), el_sign * x_deg, rtol=_RTOL, atol=1e-12
    )


@pytest.mark.parametrize("z_deg", [-40.0, 20.0, 90.0])
@pytest.mark.parametrize("x_deg", [-60.0, 0.0, 30.0, 90.0])
@pytest.mark.parametrize("y_deg", [0.0, 180.0])
def test_build_mount_rotation_matrix_pan_keeps_tilt(
    x_deg: float, y_deg: float, z_deg: float
) -> None:
    """Pan swings the boresight about the room's vertical without changing its
    tilt above or below the horizontal."""
    without_pan = build_mount_rotation_matrix(x_deg, y_deg).matrix @ [0.0, 1.0, 0.0]
    with_pan = build_mount_rotation_matrix(x_deg, y_deg, z_deg).matrix @ [0.0, 1.0, 0.0]
    np.testing.assert_allclose(with_pan[2], without_pan[2], rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize("z_deg", [-40.0, 20.0, 90.0])
@pytest.mark.parametrize("x_deg", [-60.0, 0.0, 30.0, 90.0])
@pytest.mark.parametrize(("y_deg", "az_sign"), [(0.0, -1.0), (180.0, 1.0)])
def test_build_mount_rotation_matrix_pan_sensor_azimuth(
    x_deg: float, y_deg: float, az_sign: float, z_deg: float
) -> None:
    """Relative to the un-panned mount, a pan of ``θ`` moves the boresight to
    sensor azimuth ``∓asin(sin θ · cos x_rotation)``: ``-θ`` without tilt or
    roll, ``+θ`` with ``y_rotation=180``, and zero when looking straight up."""
    without_pan = build_mount_rotation_matrix(x_deg, y_deg).matrix
    boresight = build_mount_rotation_matrix(x_deg, y_deg, z_deg).matrix @ [0.0, 1.0, 0.0]
    x, _, _ = without_pan.T @ boresight

    expected_az = az_sign * np.arcsin(np.sin(np.deg2rad(z_deg)) * np.cos(np.deg2rad(x_deg)))
    np.testing.assert_allclose(np.arcsin(x), expected_az, rtol=_RTOL, atol=1e-12)


# --- RigidTransformNode ---


@pytest.mark.parametrize("bad_t", [(0.0, 0.0), (0.0, 0.0, 0.0, 0.0)])
def test_rigid_transform_node_invalid_translation_shape_raises(
    bad_t: tuple[float, ...],
) -> None:
    """A translation vector that is not length-3 must be rejected."""
    with pytest.raises(ValueError, match=r"translation must have shape \(3,\)"):
        RigidTransformNode(rotation=RotationMatrix(), translation=bad_t)  # type: ignore[arg-type]


def test_rigid_transform_node_identity_is_passthrough() -> None:
    """Identity rotation + zero translation must return the input unchanged."""
    rng = np.random.default_rng(0)
    pts = _random_points(rng, (_NUM_SAMPLES, 3))
    out = RigidTransformNode(rotation=RotationMatrix()).execute(pts)
    np.testing.assert_allclose(out, pts, rtol=_RTOL, atol=_ATOL)


def test_rigid_transform_node_pure_rotation_preserves_magnitudes() -> None:
    """Pure rotation (zero translation) preserves per-point Euclidean norms."""
    rng = np.random.default_rng(1)
    pts = _random_points(rng, (_NUM_SAMPLES, 3))
    R = RotationMatrix(x_deg=15.0, y_deg=-25.0, z_deg=40.0)
    out = RigidTransformNode(rotation=R).execute(pts)
    np.testing.assert_allclose(
        np.linalg.norm(out, axis=-1),
        np.linalg.norm(pts, axis=-1),
        rtol=_RTOL,
        atol=_ATOL,
    )


def test_rigid_transform_node_pure_translation_shifts_uniformly() -> None:
    """With ``R = I`` the per-point delta must equal the translation."""
    rng = np.random.default_rng(2)
    pts = _random_points(rng, (_NUM_SAMPLES, 3))
    t = (1.5, -2.5, 0.75)
    out = RigidTransformNode(rotation=RotationMatrix(), translation=t).execute(pts)
    expected = np.broadcast_to(np.array(t), pts.shape)
    np.testing.assert_allclose(out - pts, expected, rtol=_RTOL, atol=_ATOL)


def test_rigid_transform_node_matches_reference() -> None:
    """``execute`` equals an independent ``R @ p + t`` over a random batch."""
    rng = np.random.default_rng(3)
    pts = _random_points(rng, (_NUM_SAMPLES, 3))
    R = RotationMatrix(x_deg=10.0, y_deg=20.0, z_deg=30.0)
    t = (0.5, -1.0, 2.0)
    out = RigidTransformNode(rotation=R, translation=t).execute(pts)
    expected = pts @ R.matrix.T + np.array(t)
    np.testing.assert_allclose(out, expected, rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize("shape", [(3,), (5, 3), (2, 4, 3)])
def test_rigid_transform_node_preserves_shape(shape: tuple[int, ...]) -> None:
    """Output shape must equal input shape for any number of leading dims."""
    rng = np.random.default_rng(4)
    pts = _random_points(rng, shape)
    node = RigidTransformNode(
        rotation=RotationMatrix(z_deg=45.0),
        translation=(1.0, 0.0, 0.0),
    )
    out = node.execute(pts)
    assert out.shape == shape


@pytest.mark.parametrize("bad_shape", [(5, 2), (5, 4), ()])
def test_rigid_transform_node_invalid_last_axis_raises(bad_shape: tuple[int, ...]) -> None:
    """Input whose last axis is not 3 must raise ``ValueError``."""
    pts = np.zeros(bad_shape)
    node = RigidTransformNode(rotation=RotationMatrix())
    with pytest.raises(ValueError, match=r"must have shape \(\.\.\., 3\)"):
        node.execute(pts)


def test_rigid_transform_node_accepts_list_of_tuples() -> None:
    """``np.asarray`` normalisation must accept ``ArrayLike`` (list of tuples)."""
    pts_list = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    node = RigidTransformNode(rotation=RotationMatrix(), translation=(1.0, 1.0, 1.0))
    out = node.execute(pts_list)
    np.testing.assert_allclose(out, [[2.0, 3.0, 4.0], [5.0, 6.0, 7.0]], rtol=_RTOL, atol=_ATOL)


# --- SphericalToCartesianNode ---


def test_spherical_to_cartesian_boresight() -> None:
    """``(d=r, az=0, el=0)`` projects to ``(0, r, 0)`` (boresight is +y)."""
    out = SphericalToCartesianNode().execute([(2.0, 0.0, 0.0)])
    np.testing.assert_allclose(out, [[0.0, 2.0, 0.0]], rtol=_RTOL, atol=_ATOL)


def test_spherical_to_cartesian_positive_azimuth_to_x() -> None:
    """``(d=r, az=90, el=0)`` projects to ``(r, 0, 0)`` — datasheet ``+az → +x``."""
    out = SphericalToCartesianNode().execute([(3.0, 90.0, 0.0)])
    np.testing.assert_allclose(out, [[3.0, 0.0, 0.0]], rtol=_RTOL, atol=_ATOL)


def test_spherical_to_cartesian_positive_elevation_to_z() -> None:
    """``(d=r, az=0, el=90)`` projects to ``(0, 0, r)``."""
    out = SphericalToCartesianNode().execute([(4.0, 0.0, 90.0)])
    np.testing.assert_allclose(out, [[0.0, 0.0, 4.0]], rtol=_RTOL, atol=_ATOL)


def test_spherical_to_cartesian_az_at_plus_90_independent_of_el() -> None:
    """Datasheet: ``az=+90°`` lands on +x regardless of elevation
    (``cos(az)=0`` zeros out y and z)."""
    out = SphericalToCartesianNode().execute(
        [(1.0, 90.0, 0.0), (1.0, 90.0, 45.0), (1.0, 90.0, -30.0)]
    )
    np.testing.assert_allclose(
        out,
        [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        rtol=_RTOL,
        atol=_ATOL,
    )


def test_spherical_to_cartesian_preserves_magnitude() -> None:
    """``sqrt(x² + y² + z²) == d`` for any ``(az, el)``."""
    rng = np.random.default_rng(7)
    pts = _random_spherical(rng, _NUM_SAMPLES)
    out = SphericalToCartesianNode().execute(pts)
    np.testing.assert_allclose(np.linalg.norm(out, axis=-1), pts[:, 0], rtol=_RTOL, atol=_ATOL)


def test_spherical_to_cartesian_distance_linearity() -> None:
    """Scaling ``d`` by ``k`` scales the Cartesian output by ``k``."""
    rng = np.random.default_rng(8)
    pts = _random_spherical(rng, _NUM_SAMPLES)
    pts_scaled = pts.copy()
    pts_scaled[:, 0] *= 2.5
    node = SphericalToCartesianNode()
    out_1 = node.execute(pts)
    out_2 = node.execute(pts_scaled)
    np.testing.assert_allclose(out_2, 2.5 * out_1, rtol=_RTOL, atol=_ATOL)


def test_spherical_to_cartesian_matches_reference() -> None:
    """Match an independent re-implementation of the datasheet projection formula
    (eqs. 16.2–16.4)."""
    rng = np.random.default_rng(9)
    pts = _random_spherical(rng, _NUM_SAMPLES)
    d = pts[:, 0]
    az = np.deg2rad(pts[:, 1])
    el = np.deg2rad(pts[:, 2])
    expected = np.stack(
        [d * np.sin(az), d * np.cos(az) * np.cos(el), d * np.cos(az) * np.sin(el)],
        axis=-1,
    )
    out = SphericalToCartesianNode().execute(pts)
    np.testing.assert_allclose(out, expected, rtol=_RTOL, atol=_ATOL)


@pytest.mark.parametrize("shape", [(3,), (5, 3), (2, 4, 3)])
def test_spherical_to_cartesian_preserves_shape(shape: tuple[int, ...]) -> None:
    """Output shape equals input shape for any number of leading dims."""
    rng = np.random.default_rng(10)
    pts = rng.uniform(0.0, 1.0, size=shape)
    out = SphericalToCartesianNode().execute(pts)
    assert out.shape == shape


@pytest.mark.parametrize("bad_shape", [(5, 2), (5, 4), ()])
def test_spherical_to_cartesian_invalid_last_axis_raises(bad_shape: tuple[int, ...]) -> None:
    """Input whose last axis is not 3 must raise ``ValueError``."""
    pts = np.zeros(bad_shape)
    with pytest.raises(ValueError, match=r"must have shape \(\.\.\., 3\)"):
        SphericalToCartesianNode().execute(pts)


def test_spherical_to_cartesian_accepts_list_of_tuples() -> None:
    """``np.asarray`` normalisation must accept ``ArrayLike`` (list of tuples)."""
    pts_list = [(1.0, 0.0, 0.0), (2.0, 90.0, 0.0)]
    out = SphericalToCartesianNode().execute(pts_list)
    np.testing.assert_allclose(out, [[0.0, 1.0, 0.0], [2.0, 0.0, 0.0]], rtol=_RTOL, atol=_ATOL)
