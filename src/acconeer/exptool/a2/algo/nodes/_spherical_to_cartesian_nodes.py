# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool.utils import spherical_to_cartesian


_NDf64 = npt.NDArray[np.float64]


@attrs.frozen
class RotationMatrix:
    """3D rotation in SO(3) composed of rotations about the fixed x, y and z axes.

    ``R = Rz(z_deg) @ Rx(x_deg) @ Ry(y_deg)`` rotates a vector ``v`` to
    ``R @ v`` (:meth:`apply`): about the fixed ``y`` axis first, then ``x``,
    then ``z`` (extrinsic). Each axis-rotation follows the right-handed
    convention. The inverse ``R.T @ v`` (:meth:`apply_inverse`) undoes them in
    the opposite order: ``-z_deg``, then ``-x_deg``, then ``-y_deg``.

    :param x_deg: Rotation around the x-axis (degrees).
    :param y_deg: Rotation around the y-axis (degrees).
    :param z_deg: Rotation around the z-axis (degrees).
    """

    x_deg: float = 0.0
    y_deg: float = 0.0
    z_deg: float = 0.0
    matrix: _NDf64 = attrs.field(init=False, eq=False, repr=False)

    @matrix.default
    def _compute_matrix(self) -> _NDf64:
        x_rad = float(np.deg2rad(self.x_deg))
        y_rad = float(np.deg2rad(self.y_deg))
        z_rad = float(np.deg2rad(self.z_deg))

        cos_x = np.cos(x_rad)
        sin_x = np.sin(x_rad)
        cos_y = np.cos(y_rad)
        sin_y = np.sin(y_rad)
        cos_z = np.cos(z_rad)
        sin_z = np.sin(z_rad)

        rx = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, cos_x, -sin_x],
                [0.0, sin_x, cos_x],
            ],
            dtype=np.float64,
        )
        ry = np.array(
            [
                [cos_y, 0.0, sin_y],
                [0.0, 1.0, 0.0],
                [-sin_y, 0.0, cos_y],
            ],
            dtype=np.float64,
        )
        rz = np.array(
            [
                [cos_z, -sin_z, 0.0],
                [sin_z, cos_z, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        return rz @ rx @ ry

    def apply(self, points: npt.ArrayLike) -> _NDf64:
        """``R @ p`` for every point ``p`` along the last axis of ``points``.

        :param points: Array-like of shape ``(..., 3)``.
        :returns: Rotated points, same shape as ``points``.
        """
        rotated: _NDf64 = np.asarray(points, dtype=np.float64) @ self.matrix.T
        return rotated

    def apply_inverse(self, points: npt.ArrayLike) -> _NDf64:
        """``R.T @ p``, the inverse rotation, for every point ``p`` along the
        last axis of ``points``.

        :param points: Array-like of shape ``(..., 3)``.
        :returns: Rotated points, same shape as ``points``.
        """
        rotated: _NDf64 = np.asarray(points, dtype=np.float64) @ self.matrix
        return rotated


def build_mount_rotation_matrix(
    x_rotation: float = 0.0, y_rotation: float = 0.0, z_rotation: float = 0.0
) -> RotationMatrix:
    """Build the mount rotation ``R = Rz(z_rotation) @ Rx(x_rotation) @ Ry(y_rotation)``.

    The angles describe the mount: start with the sensor aligned with the
    room (``+x`` right, ``+y`` boresight, ``+z`` up) and rotate it about these
    original axes, right-handed, by roll (``y``), then tilt (``x``), then pan
    (``z``). ``R`` takes sensor coordinates to room coordinates,
    ``p_room = R @ p_sensor`` (:meth:`RotationMatrix.apply`). The reverse,
    ``p_sensor = R.T @ p_room`` (:meth:`RotationMatrix.apply_inverse`), undoes
    the mount in the opposite order.

    :param x_rotation: Tilt (degrees).
    :param y_rotation: Roll (degrees).
    :param z_rotation: Pan (degrees).
    :returns: :class:`RotationMatrix` representing the composed rotation.
    """
    return RotationMatrix(x_deg=x_rotation, y_deg=y_rotation, z_deg=z_rotation)


class RigidTransformNode:
    """Applies a rigid transform ``p' = R @ p + t`` to a set of 3D points.

    The transform preserves distances and angles between points (rotation +
    translation only; no scaling, shearing, or reflection).
    """

    def __init__(
        self,
        rotation: RotationMatrix,
        translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        """
        :param rotation: :class:`RotationMatrix`.
        :param translation: Translation vector ``(tx, ty, tz)`` in metres.
            Defaults to no translation.
        :raises ValueError: If *translation* does not have shape ``(3,)``.
        """
        translation_vec = np.asarray(translation, dtype=np.float64)
        if translation_vec.shape != (3,):
            msg = f"translation must have shape (3,); got {translation_vec.shape}"
            raise ValueError(msg)

        self._rotation = rotation
        self._translation = translation_vec

    def execute(self, points: npt.ArrayLike) -> _NDf64:
        """Apply the rigid transform to a set of 3D points.

        :param points: Array-like of shape ``(..., 3)`` where the last axis
            holds ``(x, y, z)``.
        :returns: Array of the same shape with the transformed coordinates
            along the last axis.
        :raises ValueError: If the last axis of *points* is not of length 3.
        """
        pts = np.asarray(points, dtype=np.float64)
        if pts.ndim < 1 or pts.shape[-1] != 3:
            msg = f"points must have shape (..., 3); got shape {pts.shape}"
            raise ValueError(msg)

        transformed = self._rotation.apply(pts) + self._translation

        return transformed


class SphericalToCartesianNode:
    """Convert spherical (azimuth, elevation, distance) coordinates to sensor-frame Cartesian (x, y, z).

    - y: along boresight (distance at az=0, el=0)
    - x: positive azimuth → positive x (``x = d·sin(az)``), independent of elevation
    - z: positive elevation → positive z (at az=0)
    """

    def execute(self, spherical_points: npt.ArrayLike) -> _NDf64:
        """Convert spherical coordinates to sensor-frame Cartesian coordinates.

        :param spherical_points: Array-like of shape ``(..., 3)`` where the last
            axis holds ``(d, az, el)``: slant range in metres, azimuth in
            degrees, elevation in degrees.
        :returns: Array of the same shape with ``(x, y, z)`` in metres along the
            last axis.
        :raises ValueError: If the last axis of *spherical_points* is not of
            length 3.
        """
        points = np.asarray(spherical_points, dtype=np.float64)
        if points.ndim < 1 or points.shape[-1] != 3:
            msg = f"spherical_points must have shape (..., 3); got shape {points.shape}"
            raise ValueError(msg)

        dist_m = points[..., 0]
        az_rad = np.deg2rad(points[..., 1])
        el_rad = np.deg2rad(points[..., 2])

        x, y, z = spherical_to_cartesian(dist_m, az_rad, el_rad)
        cartesian_points: _NDf64 = np.stack((x, y, z), axis=-1)

        return cartesian_points
