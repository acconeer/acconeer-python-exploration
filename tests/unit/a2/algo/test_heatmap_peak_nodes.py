# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for the public nodes in ``_heatmap_peak_nodes``:

* ``PeakToListNode`` — extracts a named field from each peak in a list.
* ``PeakFuseNode`` — fuses parallel ``Peak1D`` and ``Peak2D`` lists into a
  ``Peak3D`` list.
* ``Peak3DSphericalToCartesianNode`` — composes ``SphericalToCartesianNode``
  and ``RigidTransformNode`` (mount rotation) to project ``Peak3D`` polar
  positions to ``Peak3DCart``.
* ``Peak3DCartBoxFilterNode`` — drops ``Peak3DCart`` entries whose
  ``cartesian_position`` falls outside an axis-aligned box.
* ``Peak3DCartExclusionZoneNode`` — drops ``Peak3DCart`` entries located
  inside any configured circular xy ``ExclusionZone``.
* ``Peak3DCartXYNMSNode`` — greedy non-maximum suppression on ``Peak3DCart`` lists by
  Cartesian (x, y) distance.

Tests cover canonical inputs with hand-derived expected output, empty-input
handling, field pass-through (index / amplitude / spherical_position), order
preservation, and — for ``Peak3DSphericalToCartesianNode`` — the composition
contract (mount rotation around z / y axes). The projection math itself is
the job of ``test_spherical_to_cartesian_nodes``; these tests pin the
composition only.
"""

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool.a2.algo.nodes._heatmap_peak_nodes import (
    ExclusionZone,
    Peak3D,
    Peak3DCart,
    Peak3DCartBoxFilterNode,
    Peak3DCartExclusionZoneNode,
    Peak3DCartXYNMSNode,
    Peak3DSphericalToCartesianNode,
    PeakFuseNode,
    PeakToListNode,
)
from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import Peak1D, Peak2D
from acconeer.exptool.a2.algo.nodes._spherical_to_cartesian_nodes import (
    build_mount_rotation_matrix,
)


_NDf64 = npt.NDArray[np.float64]

_RTOL = 1e-12
_ATOL = 1e-15


# --- Helpers ---


def _cart(x: float, y: float, amplitude: float, z: float = 0.0) -> Peak3DCart:
    """Build a Peak3DCart with the (x, y) coords relevant to NMS."""
    return Peak3DCart(
        index=(0, 0, 0),
        amplitude=amplitude,
        spherical_position=(0.0, 0.0, 0.0),
        cartesian_position=(x, y, z),
    )


def _gaussian_1d(coords: _NDf64, mu: float, sigma: float = 1.0) -> _NDf64:
    """Sample a 1D Gaussian at ``coords``."""
    return t.cast(_NDf64, np.exp(-0.5 * ((coords - mu) / sigma) ** 2).astype(np.float64))


# --- PeakToListNode ---


class TestPeakToListNode:
    def test_empty_input(self) -> None:
        assert PeakToListNode(field="index").execute([]) == []

    def test_extract_index_from_peak2d(self) -> None:
        peaks = [
            Peak2D(index=(0, 1), amplitude=1.0, position=(0.0, 0.0)),
            Peak2D(index=(2, 3), amplitude=2.0, position=(0.0, 0.0)),
        ]
        assert PeakToListNode(field="index").execute(peaks) == [(0, 1), (2, 3)]

    def test_extract_amplitude_from_peak2d(self) -> None:
        peaks = [
            Peak2D(index=(0, 0), amplitude=1.5, position=(0.0, 0.0)),
            Peak2D(index=(0, 0), amplitude=2.5, position=(0.0, 0.0)),
        ]
        assert PeakToListNode(field="amplitude").execute(peaks) == [1.5, 2.5]

    def test_extract_position_from_peak2d(self) -> None:
        peaks = [
            Peak2D(index=(0, 0), amplitude=0.0, position=(0.5, 1.0)),
            Peak2D(index=(0, 0), amplitude=0.0, position=(0.6, 2.0)),
        ]
        assert PeakToListNode(field="position").execute(peaks) == [(0.5, 1.0), (0.6, 2.0)]


# --- PeakFuseNode ---


class TestPeakFuseNode:
    def test_empty_input(self) -> None:
        assert PeakFuseNode().execute([], []) == []

    def test_single_pair_fuses_indices_positions_and_amplitude(self) -> None:
        p1 = Peak1D(index=3, amplitude=0.7, position=1.5)
        p2 = Peak2D(index=(1, 2), amplitude=7.5, position=(0.42, 33.0))

        (out,) = PeakFuseNode().execute([p1], [p2])

        assert out.index == (1, 2, 3)
        # Amplitude is taken from Peak2D, NOT from Peak1D.
        assert out.amplitude == 7.5
        assert out.position == (0.42, 33.0, 1.5)

    def test_order_preserved(self) -> None:
        p1s = [
            Peak1D(index=1, amplitude=0.0, position=10.0),
            Peak1D(index=2, amplitude=0.0, position=20.0),
            Peak1D(index=3, amplitude=0.0, position=30.0),
        ]
        p2s = [
            Peak2D(index=(0, 0), amplitude=1.0, position=(0.0, 0.0)),
            Peak2D(index=(1, 1), amplitude=2.0, position=(0.1, 0.1)),
            Peak2D(index=(2, 2), amplitude=3.0, position=(0.2, 0.2)),
        ]
        out = PeakFuseNode().execute(p1s, p2s)
        assert [p.index for p in out] == [(0, 0, 1), (1, 1, 2), (2, 2, 3)]

    def test_length_mismatch_raises(self) -> None:
        p1s = [Peak1D(index=0, amplitude=0.0, position=0.0)]
        p2s: list[Peak2D] = []
        with pytest.raises(ValueError, match="same length"):
            PeakFuseNode().execute(p1s, p2s)


# --- Peak3DSphericalToCartesianNode ---


class TestPeak3DSphericalToCartesianNode:
    def test_empty_input(self) -> None:
        assert Peak3DSphericalToCartesianNode().execute([]) == []

    def test_no_offset_no_bounds_matches_direct_projection(self) -> None:
        peak = Peak3D(index=(0, 0, 0), amplitude=1.0, position=(2.0, 0.0, 0.0))

        (out,) = Peak3DSphericalToCartesianNode().execute([peak])

        # Boresight (az=0, el=0) lands on +y under the datasheet convention.
        assert out.cartesian_position == pytest.approx((0.0, 2.0, 0.0), rel=_RTOL, abs=_ATOL)

    def test_pass_through_fields(self) -> None:
        peak = Peak3D(index=(1, 2, 3), amplitude=4.5, position=(2.0, 30.0, 10.0))

        (out,) = Peak3DSphericalToCartesianNode().execute([peak])

        assert out.index == (1, 2, 3)
        assert out.amplitude == 4.5
        assert out.spherical_position == (2.0, 30.0, 10.0)

    def test_z_rotation_rotates_about_z(self) -> None:
        # Boresight peak (x=0, y=2, z=0) rotated by z_rotation=90° -> (-2, 0, 0)
        # (standard right-handed rotation about z: +x toward +y, so the
        # boresight +y goes toward -x -- the opposite direction from the
        # spherical +az -> +x convention; the two are independent).
        peak = Peak3D(index=(0, 0, 0), amplitude=1.0, position=(2.0, 0.0, 0.0))

        node = Peak3DSphericalToCartesianNode(build_mount_rotation_matrix(z_rotation=90.0))
        (out,) = node.execute([peak])

        assert out.cartesian_position == pytest.approx((-2.0, 0.0, 0.0), rel=_RTOL, abs=_ATOL)

    def test_x_rotation_tilts_about_x(self) -> None:
        # Boresight peak (x=0, y=2, z=0) tilted by x_rotation=90° -> (0, 0, 2).
        # build_mount_rotation_matrix(x_rotation=90) = Rz(0) @ Rx(90); Rx(90)
        # maps (0, 2, 0) -> (0, 0, 2).
        peak = Peak3D(index=(0, 0, 0), amplitude=1.0, position=(2.0, 0.0, 0.0))

        node = Peak3DSphericalToCartesianNode(build_mount_rotation_matrix(x_rotation=90.0))
        (out,) = node.execute([peak])

        assert out.cartesian_position == pytest.approx((0.0, 0.0, 2.0), rel=_RTOL, abs=_ATOL)

    def test_y_rotation_rotates_about_y(self) -> None:
        # A peak off the boresight axis (raw az=90 -> raw cartesian (2, 0, 0))
        # rolled by 90° about the boresight (y-axis) -> (0, 0, -2).
        # Ry(90) maps (x, y, z) -> (x*cos90 + z*sin90, y, -x*sin90 + z*cos90);
        # at (2, 0, 0): -> (0, 0, -2).
        peak = Peak3D(index=(0, 0, 0), amplitude=1.0, position=(2.0, 90.0, 0.0))

        node = Peak3DSphericalToCartesianNode(build_mount_rotation_matrix(y_rotation=90.0))
        (out,) = node.execute([peak])

        assert out.cartesian_position == pytest.approx((0.0, 0.0, -2.0), rel=_RTOL, abs=_ATOL)

    def test_y_rotation_leaves_boresight_peak_unchanged(self) -> None:
        # A peak exactly on the boresight (raw az=0, el=0) already lies on
        # the roll axis, so rolling around it has no effect.
        peak = Peak3D(index=(0, 0, 0), amplitude=1.0, position=(2.0, 0.0, 0.0))

        node = Peak3DSphericalToCartesianNode(build_mount_rotation_matrix(y_rotation=45.0))
        (out,) = node.execute([peak])

        assert out.cartesian_position == pytest.approx((0.0, 2.0, 0.0), rel=_RTOL, abs=_ATOL)

    def test_order_preserved(self) -> None:
        peaks = [
            Peak3D(index=(0, 0, 0), amplitude=1.0, position=(2.0, 0.0, 0.0)),
            Peak3D(index=(1, 0, 0), amplitude=2.0, position=(3.0, 0.0, 0.0)),
            Peak3D(index=(2, 0, 0), amplitude=3.0, position=(4.0, 0.0, 0.0)),
        ]

        out = Peak3DSphericalToCartesianNode().execute(peaks)

        assert [p.index for p in out] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]


# --- Peak3DCartBoxFilterNode ---


def _cart_at(
    x: float, y: float, z: float, *, index: t.Tuple[int, int, int] = (0, 0, 0)
) -> Peak3DCart:
    """Build a Peak3DCart at a given Cartesian position."""
    return Peak3DCart(
        index=index,
        amplitude=1.0,
        spherical_position=(0.0, 0.0, 0.0),
        cartesian_position=(x, y, z),
    )


class TestPeak3DCartBoxFilterNode:
    @pytest.mark.parametrize("axis_name", ["x_bounds_m", "y_bounds_m", "z_bounds_m"])
    def test_lo_ge_hi_raises(self, axis_name: str) -> None:
        bad = {axis_name: (1.0, 1.0)}
        with pytest.raises(ValueError, match=axis_name):
            Peak3DCartBoxFilterNode(**bad)  # type: ignore[arg-type]

    @pytest.mark.parametrize("axis_name", ["x_bounds_m", "y_bounds_m", "z_bounds_m"])
    def test_wrong_length_raises(self, axis_name: str) -> None:
        bad = {axis_name: (0.0, 1.0, 2.0)}
        with pytest.raises(ValueError, match=axis_name):
            Peak3DCartBoxFilterNode(**bad)  # type: ignore[arg-type]

    def test_empty_input(self) -> None:
        assert Peak3DCartBoxFilterNode(x_bounds_m=(0.0, 1.0)).execute([]) == []

    def test_no_bounds_keeps_everything(self) -> None:
        peaks = [
            _cart_at(100.0, -100.0, 100.0),
            _cart_at(-0.01, 0.0, 0.0),
        ]
        out = Peak3DCartBoxFilterNode().execute(peaks)
        assert out == peaks

    def test_single_axis_bound(self) -> None:
        # Only x is constrained; y and z values don't matter.
        peaks = [
            _cart_at(0.5, 100.0, -100.0, index=(0, 0, 0)),  # kept
            _cart_at(2.0, -50.0, 50.0, index=(1, 0, 0)),  # dropped (x > 1)
            _cart_at(-1.0, 0.0, 0.0, index=(2, 0, 0)),  # dropped (x < 0)
        ]
        out = Peak3DCartBoxFilterNode(x_bounds_m=(0.0, 1.0)).execute(peaks)
        assert [p.index for p in out] == [(0, 0, 0)]

    def test_all_axes_bound_is_conjunction(self) -> None:
        peaks = [
            _cart_at(0.5, 0.5, 0.5, index=(0, 0, 0)),  # kept
            _cart_at(0.5, 0.5, 2.0, index=(1, 0, 0)),  # z out
            _cart_at(0.5, 2.0, 0.5, index=(2, 0, 0)),  # y out
            _cart_at(2.0, 0.5, 0.5, index=(3, 0, 0)),  # x out
        ]
        out = Peak3DCartBoxFilterNode(
            x_bounds_m=(0.0, 1.0),
            y_bounds_m=(0.0, 1.0),
            z_bounds_m=(0.0, 1.0),
        ).execute(peaks)
        assert [p.index for p in out] == [(0, 0, 0)]

    @pytest.mark.parametrize("v", [-1.0, 1.0])
    def test_boundaries_are_inclusive(self, v: float) -> None:
        peaks = [_cart_at(v, v, v)]
        out = Peak3DCartBoxFilterNode(
            x_bounds_m=(-1.0, 1.0),
            y_bounds_m=(-1.0, 1.0),
            z_bounds_m=(-1.0, 1.0),
        ).execute(peaks)
        assert out == peaks

    def test_order_preserved(self) -> None:
        peaks = [
            _cart_at(0.1, 0.0, 0.0, index=(0, 0, 0)),
            _cart_at(0.5, 0.0, 0.0, index=(1, 0, 0)),
            _cart_at(0.9, 0.0, 0.0, index=(2, 0, 0)),
        ]
        out = Peak3DCartBoxFilterNode(x_bounds_m=(0.0, 1.0)).execute(peaks)
        assert [p.index for p in out] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]

    def test_pass_through_fields(self) -> None:
        peak = Peak3DCart(
            index=(1, 2, 3),
            amplitude=4.5,
            spherical_position=(2.0, 30.0, 10.0),
            cartesian_position=(0.5, 0.5, 0.5),
        )
        (out,) = Peak3DCartBoxFilterNode(x_bounds_m=(0.0, 1.0)).execute([peak])
        assert out is peak


# --- Peak3DCartExclusionZoneNode ---


class TestPeak3DCartExclusionZoneNode:
    def test_empty_input(self) -> None:
        node = Peak3DCartExclusionZoneNode([ExclusionZone(center=(0.0, 0.0), radius_m=1.0)])
        assert node.execute([]) == []

    def test_no_zones_keeps_everything(self) -> None:
        peaks = [_cart_at(0.0, 0.0, 0.0), _cart_at(5.0, 5.0, 0.0)]
        assert Peak3DCartExclusionZoneNode().execute(peaks) == peaks

    def test_peak_inside_zone_is_dropped(self) -> None:
        node = Peak3DCartExclusionZoneNode([ExclusionZone(center=(0.0, 0.0), radius_m=1.0)])
        peaks = [
            _cart_at(0.1, 0.0, 0.0, index=(0, 0, 0)),  # inside -> dropped
            _cart_at(5.0, 5.0, 0.0, index=(1, 0, 0)),  # outside -> kept
        ]
        out = node.execute(peaks)
        assert [p.index for p in out] == [(1, 0, 0)]

    def test_boundary_is_inclusive(self) -> None:
        node = Peak3DCartExclusionZoneNode([ExclusionZone(center=(0.0, 0.0), radius_m=1.0)])
        on_boundary = _cart_at(1.0, 0.0, 0.0)
        assert node.execute([on_boundary]) == []

    def test_multiple_zones(self) -> None:
        node = Peak3DCartExclusionZoneNode(
            [
                ExclusionZone(center=(10.0, 10.0), radius_m=1.0),
                ExclusionZone(center=(0.0, 0.0), radius_m=1.0),
            ]
        )
        peaks = [
            _cart_at(0.0, 0.0, 0.0, index=(0, 0, 0)),  # inside second zone -> dropped
            _cart_at(5.0, 5.0, 0.0, index=(1, 0, 0)),  # outside both -> kept
        ]
        out = node.execute(peaks)
        assert [p.index for p in out] == [(1, 0, 0)]

    def test_order_preserved(self) -> None:
        node = Peak3DCartExclusionZoneNode([ExclusionZone(center=(0.0, 0.0), radius_m=1.0)])
        peaks = [
            _cart_at(5.0, 5.0, 0.0, index=(0, 0, 0)),
            _cart_at(-5.0, -5.0, 0.0, index=(1, 0, 0)),
            _cart_at(3.0, 3.0, 0.0, index=(2, 0, 0)),
        ]
        out = node.execute(peaks)
        assert [p.index for p in out] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]


# --- Peak3DCartXYNMSNode ---


class TestPeak3DCartXYNMSNode:
    def test_empty_input(self) -> None:
        assert Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([]) == []

    def test_no_suppression_when_far_apart(self) -> None:
        peaks = [_cart(0.0, 0.0, 5.0), _cart(2.0, 0.0, 3.0)]
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute(peaks)
        assert out == peaks

    def test_close_peak_suppressed(self) -> None:
        # Two peaks 0.5 m apart with separation threshold 1.0 m: only the highest survives.
        high = _cart(0.0, 0.0, 5.0)
        low = _cart(0.5, 0.0, 3.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([high, low])
        assert out == [high]

    def test_output_in_amplitude_descending_order(self) -> None:
        # Input is amplitude-descending; survivors must keep that order.
        p1 = _cart(0.0, 0.0, 10.0)
        p2 = _cart(3.0, 0.0, 7.0)
        p3 = _cart(6.0, 0.0, 4.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([p1, p2, p3])
        assert out == [p1, p2, p3]

    def test_sorts_unordered_input_by_amplitude_descending(self) -> None:
        # Input is NOT amplitude-descending: the node sorts internally so
        # the strongest peak wins over weaker, nearby ones regardless of
        # caller-provided order.
        weak = _cart(0.0, 0.0, 3.0)
        strong = _cart(0.5, 0.0, 9.0)  # 0.5 m from weak -> suppresses it
        far = _cart(5.0, 0.0, 6.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([weak, strong, far])
        # Output is amplitude-descending: strong (9.0), far (6.0); weak suppressed.
        assert out == [strong, far]

    def test_middle_amplitude_suppressed_by_highest(self) -> None:
        # The 7.0-amp peak is within 1 m of the 10.0-amp peak -> suppressed.
        # The 4.0-amp peak is far from both -> kept.
        p1 = _cart(0.0, 0.0, 10.0)
        p2 = _cart(0.5, 0.0, 7.0)
        p3 = _cart(5.0, 0.0, 4.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([p1, p2, p3])
        assert out == [p1, p3]

    def test_only_xy_used_for_distance(self) -> None:
        # Two peaks at identical (x, y) but very different z: must be suppressed
        # (distance is np.hypot(dx, dy) only).
        p1 = _cart(0.0, 0.0, 5.0, z=0.0)
        p2 = _cart(0.0, 0.0, 4.0, z=10.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=0.1).execute([p1, p2])
        assert out == [p1]

    def test_distance_uses_y_axis(self) -> None:
        # Verify the y component participates: peaks on the y axis 0.5 m apart
        # are suppressed at threshold 1.0 m.
        p1 = _cart(0.0, 0.0, 5.0)
        p2 = _cart(0.0, 0.5, 3.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([p1, p2])
        assert out == [p1]

    def test_separation_threshold_is_strict_below(self) -> None:
        # Distance == threshold is NOT suppressed (the check is ``< min_dist``).
        p1 = _cart(0.0, 0.0, 5.0)
        p2 = _cart(1.0, 0.0, 3.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([p1, p2])
        assert out == [p1, p2]

    def test_zero_threshold_accepts_all_distinct(self) -> None:
        peaks = [_cart(0.0, 0.0, 5.0), _cart(0.0, 0.0, 4.0)]
        # min_dist=0.0 -> distance (0.0) is not strictly less than 0.0 -> both kept.
        out = Peak3DCartXYNMSNode(min_dist_separation_m=0.0).execute(peaks)
        assert out == peaks

    def test_negative_min_dist_raises(self) -> None:
        with pytest.raises(ValueError, match="min_dist_separation_m"):
            Peak3DCartXYNMSNode(min_dist_separation_m=-0.1)

    def test_equal_amplitude_tie_preserves_input_order(self) -> None:
        # Two equal-amplitude peaks, > min_dist apart so both survive.
        # Python's sort is stable, so input order must be preserved.
        first = _cart(0.0, 0.0, 5.0)
        second = _cart(3.0, 0.0, 5.0)
        out = Peak3DCartXYNMSNode(min_dist_separation_m=1.0).execute([first, second])
        assert out == [first, second]
