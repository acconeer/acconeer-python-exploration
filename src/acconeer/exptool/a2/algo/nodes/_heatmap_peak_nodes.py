# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import (
    Peak1D,
    Peak2D,
)
from acconeer.exptool.a2.algo.nodes._spherical_to_cartesian_nodes import (
    RigidTransformNode,
    RotationMatrix,
    SphericalToCartesianNode,
)


_NDf64 = npt.NDArray[np.float64]


@attrs.frozen
class Peak3D:
    """Detected and interpolated peak in a 3D (D, AZ, EL) heatmap."""

    index: t.Tuple[int, int, int]
    """(D, AZ, EL) peak index."""

    amplitude: float
    """The heatmap amplitude/power at the peak index."""

    position: t.Tuple[float, float, float]
    """(dist_m, az_deg, el_deg) interpolated peak position."""


@attrs.frozen
class Peak3DCart:
    """Detected and interpolated peak in a 3D heatmap with Cartesian position appended."""

    index: t.Tuple[int, int, int]
    """(D, AZ, EL) peak index."""

    amplitude: float
    """The heatmap amplitude/power at the peak index."""

    spherical_position: t.Tuple[float, float, float]
    """(dist_m, az_deg, el_deg) interpolated peak position."""

    cartesian_position: t.Tuple[float, float, float]
    """(x, y, z) interpolated peak position in metres."""


_PeakField = t.Literal["index", "amplitude", "position"]


class PeakToListNode:
    """Extracts a named field from each peak in a list.

    Useful for handing peak indices/positions to downstream nodes that don't
    need the full peak record — e.g. feeding ``Peak2D.index`` tuples into
    :class:`IndexedSliceStackNode`.
    """

    def __init__(self, field: _PeakField) -> None:
        self.field = field

    def execute(self, peaks: t.Sequence[t.Any]) -> t.List[t.Any]:
        return [getattr(p, self.field) for p in peaks]


class PeakFuseNode:
    """Fuses parallel ``Peak1D`` and ``Peak2D`` lists into a ``Peak3D`` list.

    For each row ``i``, builds ``Peak3D(index=(peak2d.index + (peak1d.index,)),
    amplitude=peak2d.amplitude, position=(peak2d.position + (peak1d.position,)))``.

    Amplitude is taken from :class:`Peak2D` — it's the canonical "what CFAR
    saw" value and is well-defined regardless of whether a full 3D heatmap
    was materialised.
    """

    def execute(
        self,
        peaks_1d: t.Sequence[Peak1D],
        peaks_2d: t.Sequence[Peak2D],
    ) -> t.List[Peak3D]:
        if len(peaks_1d) != len(peaks_2d):
            msg = (
                f"peaks_1d and peaks_2d must have the same length, "
                f"got {len(peaks_1d)} and {len(peaks_2d)}"
            )
            raise ValueError(msg)
        return [
            Peak3D(
                index=(p2.index[0], p2.index[1], p1.index),
                amplitude=p2.amplitude,
                position=(p2.position[0], p2.position[1], p1.position),
            )
            for p1, p2 in zip(peaks_1d, peaks_2d)
        ]


class Peak3DSphericalToCartesianNode:
    """Converts the interpolated polar position of :class:`Peak3D` objects to Cartesian coordinates.

    Composes :class:`SphericalToCartesianNode` (spherical → sensor-centred
    Cartesian) and :class:`RigidTransformNode` (applies the mount rotation) to
    convert each :class:`Peak3D` into a :class:`Peak3DCart`. Output Cartesian
    positions are sensor-centred with axes rotated by the mount offsets. Every
    input peak yields one output; order is preserved.

    Intended as a post-processing step after :class:`PeakFuseNode`.
    """

    def __init__(self, rotation: t.Optional[RotationMatrix] = None) -> None:
        """
        :param rotation: Mount :class:`RotationMatrix`, typically from
            :func:`build_mount_rotation_matrix`; maps sensor-frame positions
            to the mount-rotated frame. ``None`` means no rotation.
        """
        self._sphere = SphericalToCartesianNode()
        self._mount_rot = RigidTransformNode(
            rotation=RotationMatrix() if rotation is None else rotation,
        )

    def execute(self, peaks: t.List[Peak3D]) -> t.List[Peak3DCart]:
        """Convert polar peak positions to Cartesian.

        :param peaks: List of :class:`Peak3D` objects, typically from
            :class:`PeakFuseNode`.
        :returns: List of :class:`Peak3DCart` in the sensor-centred,
            mount-rotated frame, preserving the original order. Every input
            peak yields one output.
        """
        if not peaks:
            return []

        spherical_points = np.array([p.position for p in peaks], dtype=np.float64)
        cart = self._mount_rot.execute(self._sphere.execute(spherical_points))

        return [
            Peak3DCart(
                index=peak.index,
                amplitude=peak.amplitude,
                spherical_position=peak.position,
                cartesian_position=(float(cart_pos[0]), float(cart_pos[1]), float(cart_pos[2])),
            )
            for peak, cart_pos in zip(peaks, cart)
        ]


class Peak3DCartBoxFilterNode:
    """Drops :class:`Peak3DCart` objects whose ``cartesian_position`` falls outside an axis-aligned box.

    The box is defined by per-axis ``(lo, hi)`` bounds. Each axis bound is
    optional: ``None`` means the axis is unconstrained. A peak is kept when
    ``lo <= v <= hi`` holds for every constrained axis (inclusive on both
    ends). When all three bounds are ``None`` the node acts as a no-op — every
    input peak is kept.

    Intended as a post-processing step after :class:`Peak3DSphericalToCartesianNode`.
    """

    def __init__(
        self,
        x_bounds_m: t.Optional[t.Tuple[float, float]] = None,
        y_bounds_m: t.Optional[t.Tuple[float, float]] = None,
        z_bounds_m: t.Optional[t.Tuple[float, float]] = None,
    ) -> None:
        """
        :param x_bounds_m: ``(lo, hi)`` for the x-axis in metres, or ``None`` to
            leave the x-axis unconstrained. Must satisfy ``lo < hi`` when set.
        :param y_bounds_m: ``(lo, hi)`` for the y-axis, or ``None``. Same rules.
        :param z_bounds_m: ``(lo, hi)`` for the z-axis, or ``None``. Same rules.
        :raises ValueError: If any non-``None`` bounds tuple does not have
            length 2 or has ``lo >= hi``.
        """
        for name, bounds in (
            ("x_bounds_m", x_bounds_m),
            ("y_bounds_m", y_bounds_m),
            ("z_bounds_m", z_bounds_m),
        ):
            if bounds is None:
                continue
            if len(bounds) != 2:
                msg = f"{name} must have length 2; got {len(bounds)}"
                raise ValueError(msg)
            if bounds[0] >= bounds[1]:
                msg = f"{name}[0] must be < {name}[1]; got {bounds}"
                raise ValueError(msg)

        self._x_bounds_m = x_bounds_m
        self._y_bounds_m = y_bounds_m
        self._z_bounds_m = z_bounds_m

    def execute(self, peaks: t.List[Peak3DCart]) -> t.List[Peak3DCart]:
        """Drop peaks whose Cartesian position lies outside the box.

        :param peaks: List of :class:`Peak3DCart` objects, typically from
            :class:`Peak3DSphericalToCartesianNode`.
        :returns: List of :class:`Peak3DCart` in the same order, with peaks
            outside any configured axis bound omitted. With no bounds
            configured, the input list is returned unchanged.
        """
        if not peaks:
            return []

        points = np.array([p.cartesian_position for p in peaks], dtype=np.float64)
        mask: npt.NDArray[np.bool_] = np.ones(points.shape[0], dtype=np.bool_)

        if self._x_bounds_m is not None:
            x = points[:, 0]
            x_lo, x_hi = self._x_bounds_m
            mask &= (x_lo <= x) & (x <= x_hi)
        if self._y_bounds_m is not None:
            y = points[:, 1]
            y_lo, y_hi = self._y_bounds_m
            mask &= (y_lo <= y) & (y <= y_hi)
        if self._z_bounds_m is not None:
            z = points[:, 2]
            z_lo, z_hi = self._z_bounds_m
            mask &= (z_lo <= z) & (z <= z_hi)

        return [peak for peak, ok in zip(peaks, mask) if ok]


@attrs.frozen
class ExclusionZone:
    """A circular exclusion zone in the xy plane.

    ``center`` is an ``(x, y)`` cartesian position and ``radius_m`` the
    zone's radius.
    """

    center: t.Tuple[float, float]
    radius_m: float = attrs.field(validator=attrs.validators.gt(0.0))


class Peak3DCartExclusionZoneNode:
    """Drops :class:`Peak3DCart` objects located inside any configured :class:`ExclusionZone`.

    Meant to run alongside :class:`Peak3DCartBoxFilterNode` (same pipeline
    position: after :class:`Peak3DSphericalToCartesianNode`, before
    :class:`Peak3DCartXYNMSNode`): any peak whose xy position falls inside a
    zone (boundary inclusive) is dropped outright, so it never reaches
    detection-building or tracking. The zones are fixed at construction.
    """

    def __init__(self, zones: t.Sequence[ExclusionZone] = ()) -> None:
        self._zones: t.Tuple[ExclusionZone, ...] = tuple(zones)
        self._centers: npt.NDArray[np.float64] = np.array(
            [zone.center for zone in self._zones], dtype=np.float64
        ).reshape(-1, 2)
        self._radii_m: npt.NDArray[np.float64] = np.array(
            [zone.radius_m for zone in self._zones], dtype=np.float64
        )

    @property
    def zones(self) -> t.Tuple[ExclusionZone, ...]:
        return self._zones

    def execute(self, peaks: t.List[Peak3DCart]) -> t.List[Peak3DCart]:
        if not peaks or not self._zones:
            return peaks

        points = np.array([p.cartesian_position[:2] for p in peaks], dtype=np.float64)
        offsets = points[:, np.newaxis, :] - self._centers[np.newaxis, :, :]  # (peaks, zones, 2)
        inside: npt.NDArray[np.bool_] = np.any(
            np.hypot(offsets[..., 0], offsets[..., 1]) <= self._radii_m, axis=1
        )

        return [peak for peak, drop in zip(peaks, inside) if not drop]


class Peak3DCartXYNMSNode:
    """
    Greedy Non-Maximum Suppression on :class:`Peak3DCart` objects by Cartesian (x, y) distance.

    The z coordinate is ignored entirely — suppression is based on the projection
    onto the x-y plane. Sorts peaks by amplitude (descending) and suppresses any
    candidate whose ``(x, y)`` position is closer than ``min_dist_separation_m``
    to an already-accepted peak. The sort is stable, so peaks with equal
    amplitude are visited in their original input order.
    """

    def __init__(self, min_dist_separation_m: float) -> None:
        """
        :param min_dist_separation_m: Minimum (x, y) Cartesian distance between accepted peaks (metres).
            Candidates closer than this to a stronger peak are suppressed.
        :raises ValueError: If ``min_dist_separation_m < 0``.
        """
        if min_dist_separation_m < 0.0:
            msg = f"min_dist_separation_m must be >= 0.0; got {min_dist_separation_m}"
            raise ValueError(msg)
        self._min_dist_separation_m = min_dist_separation_m

    def execute(self, peaks: t.List[Peak3DCart]) -> t.List[Peak3DCart]:
        """Apply greedy NMS to a list of peaks.

        :param peaks: Peaks to filter. Input order does not matter — the node
            sorts by amplitude (descending) internally.
        :returns: Accepted peaks after suppression, in amplitude-descending order.
        """
        sorted_peaks = sorted(peaks, key=lambda p: p.amplitude, reverse=True)
        selected: t.List[Peak3DCart] = []
        for peak in sorted_peaks:
            if not self._is_suppressed(peak, selected):
                selected.append(peak)
        return selected

    def _is_suppressed(self, candidate: Peak3DCart, selected: t.List[Peak3DCart]) -> bool:
        x_c, y_c, _ = candidate.cartesian_position
        for sel in selected:
            x_s, y_s, _ = sel.cartesian_position
            if np.hypot(x_c - x_s, y_c - y_s) < self._min_dist_separation_m:
                return True
        return False
