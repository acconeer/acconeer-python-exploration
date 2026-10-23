# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for the peak-finding nodes in ``_peak_finding_nodes``:

* ``LocalMaxima1DNode``  — local maxima in a 1D array via ``scipy.ndimage.maximum_filter``
  with a configurable ``radius`` half-width and optional per-position threshold.
* ``LocalMaxima2DNode``  — local maxima in a 2D array via ``maximum_filter`` with a
  per-axis ``radii`` tuple and optional threshold.

Both nodes are stateless and pure-functional. Tests are grouped per node and cover:

  * Canonical inputs with hand-derived expected output.
  * Boundary handling.
  * Tie handling — under ``data == maximum_filter(data)`` ties at adjacent cells
    both pass; downstream NMS is expected to deduplicate near-coincident detections.
  * Uniform-region behavior — every cell of a fully-flat window is reported as a
    peak (each cell equals its local max). Callers either set a threshold above
    the noise floor or rely on downstream NMS.
  * Threshold semantics (scalar vs array, ``data >= threshold`` accepts equality).
  * Shape / dimensionality validation.
  * Radius / radii configuration: defaults reproduce the old radius-1 behaviour,
    larger values widen the suppression neighbourhood per axis.
"""

from __future__ import annotations

import numpy as np
import pytest

from acconeer.exptool.a2.algo.nodes._peak_finding_nodes import LocalMaxima1DNode, LocalMaxima2DNode


# --- LocalMaxima1DNode ---


class TestLocalMaxima1DNode:
    def test_interior_peaks(self) -> None:
        # Two clear interior peaks at indices 2 and 5. Endpoints decrease/increase
        # but the interior neighbor constraint is satisfied for them too — however
        # i=0 (0.0) is not greater than i=1 (1.0), so no boundary peak there.
        data = np.array([0.0, 1.0, 3.0, 1.0, 2.0, 4.0, 2.0])
        assert LocalMaxima1DNode().execute(data) == [2, 5]

    def test_left_boundary_peak(self) -> None:
        # i=0 only competes against i=1 (window padded with -inf on the left).
        data = np.array([5.0, 1.0, 2.0, 0.0])
        # i=0: 5 > 1 -> peak; i=2: 2 > 1 and 2 > 0 -> peak.
        assert LocalMaxima1DNode().execute(data) == [0, 2]

    def test_right_boundary_peak(self) -> None:
        # i=N-1 only competes against i=N-2 (window padded with -inf on the right).
        data = np.array([0.0, 2.0, 1.0, 3.0])
        # i=1: 2 > 0 and 2 > 1 -> peak; i=3: 3 > 1 -> peak.
        assert LocalMaxima1DNode().execute(data) == [1, 3]

    def test_adjacent_ties_both_pass(self) -> None:
        # ``data == maximum_filter(data)`` is non-strict. Adjacent cells equal to
        # the local max both qualify; downstream NMS is expected to deduplicate.
        # (The zeros lose to the 5s within their windows and are not reported.)
        data = np.array([0.0, 5.0, 5.0, 0.0])
        assert LocalMaxima1DNode().execute(data) == [1, 2]

    def test_uniform_array_reports_every_cell(self) -> None:
        # A fully flat array has every cell equal to its local max → every cell
        # is reported. Callers filter via threshold or downstream NMS.
        data = np.ones(4)
        assert LocalMaxima1DNode().execute(data) == [0, 1, 2, 3]

    def test_monotonic_increasing_only_right_boundary(self) -> None:
        data = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        assert LocalMaxima1DNode().execute(data) == [4]

    def test_monotonic_decreasing_only_left_boundary(self) -> None:
        data = np.array([4.0, 3.0, 2.0, 1.0, 0.0])
        assert LocalMaxima1DNode().execute(data) == [0]

    def test_single_element_is_peak(self) -> None:
        # N=1: the lone cell equals its window's local max (window padded with -inf
        # on both sides), so it qualifies.
        data = np.array([0.0])
        assert LocalMaxima1DNode().execute(data) == [0]

    def test_empty_input(self) -> None:
        data = np.array([], dtype=np.float64)
        assert LocalMaxima1DNode().execute(data) == []

    def test_scalar_threshold_filters_low_peaks(self) -> None:
        # Peaks at 2 (value 3.0) and 5 (value 4.0). Threshold 3.5 keeps only 5.
        data = np.array([0.0, 1.0, 3.0, 1.0, 2.0, 4.0, 2.0])
        assert LocalMaxima1DNode().execute(data, threshold=3.5) == [5]

    def test_scalar_threshold_accepts_equality(self) -> None:
        # A peak equal to the threshold is kept (``data >= threshold``).
        data = np.array([0.0, 1.0, 3.0, 1.0])
        assert LocalMaxima1DNode().execute(data, threshold=3.0) == [2]

    def test_array_threshold_per_position(self) -> None:
        # Peak at 2 (3.0) has local threshold 5.0 -> rejected.
        # Peak at 5 (4.0) has local threshold 1.0 -> kept.
        data = np.array([0.0, 1.0, 3.0, 1.0, 2.0, 4.0, 2.0])
        threshold = np.array([0.0, 0.0, 5.0, 0.0, 0.0, 1.0, 0.0])
        assert LocalMaxima1DNode().execute(data, threshold=threshold) == [5]

    def test_rejects_non_1d_input(self) -> None:
        data = np.zeros((3, 3))
        with pytest.raises(ValueError, match="1D array"):
            LocalMaxima1DNode().execute(data)

    def test_rejects_wrong_length_threshold(self) -> None:
        data = np.array([0.0, 1.0, 0.0])
        with pytest.raises(ValueError, match=r"scalar or a 1D array of shape \(3,\)"):
            LocalMaxima1DNode().execute(data, threshold=np.array([0.0, 0.0]))

    def test_rejects_higher_dim_threshold(self) -> None:
        data = np.array([0.0, 1.0, 0.0])
        with pytest.raises(ValueError, match=r"scalar or a 1D array of shape \(3,\)"):
            LocalMaxima1DNode().execute(data, threshold=np.zeros((1, 3)))

    def test_result_order_is_ascending(self) -> None:
        # Ordering is a by-product of left-to-right ``np.argwhere`` and is relied on
        # by downstream nodes. Peak values here (7, 3, 5) are deliberately not
        # monotonic so a hypothetical value-sorted implementation would produce a
        # different order.
        data = np.array([0.0, 7.0, 0.0, 0.0, 3.0, 0.0, 5.0, 0.0])
        result = LocalMaxima1DNode().execute(data)
        assert result == [1, 4, 6]
        assert result == sorted(result)

    def test_radius_2_suppresses_closer_neighbor(self) -> None:
        # ``radius=2`` widens the window to ±2 cells. Peak value 3 at index 2 has
        # a higher value 5 at index 4 (2 cells away) — within the window — so it
        # is no longer reported. With the default radius=1 it would be a peak.
        data = np.array([0.0, 1.0, 3.0, 4.0, 5.0, 0.0])
        assert LocalMaxima1DNode().execute(data) == [4]  # default radius=1 → 4 only
        assert LocalMaxima1DNode(radius=2).execute(data) == [4]  # still only 4

        # Now place two peaks 2 apart: radius=1 reports both, radius=2 keeps only
        # the higher one.
        data = np.array([0.0, 3.0, 0.0, 5.0, 0.0])
        assert LocalMaxima1DNode(radius=1).execute(data) == [1, 3]
        assert LocalMaxima1DNode(radius=2).execute(data) == [3]

    def test_radius_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="radius must be at least 1"):
            LocalMaxima1DNode(radius=0)


# --- LocalMaxima2DNode ---


class TestLocalMaxima2DNode:
    def test_single_interior_peak(self) -> None:
        # Single peak at (1, 1).
        data = np.array(
            [
                [0.0, 0.0, 0.0],
                [0.0, 5.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )
        assert LocalMaxima2DNode().execute(data) == [(1, 1)]

    def test_corner_peak(self) -> None:
        # Boundary peak at (0, 0): window padded with -inf outside the array, so it
        # only competes against (0,1), (1,0), (1,1).
        data = np.array(
            [
                [5.0, 1.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )
        assert LocalMaxima2DNode().execute(data) == [(0, 0)]

    def test_adjacent_ties_both_pass(self) -> None:
        # ``data == maximum_filter(data)`` is non-strict. Adjacent cells equal to the
        # local max both qualify; downstream NMS is expected to deduplicate.
        data = np.array(
            [
                [0.0, 0.0, 0.0],
                [0.0, 5.0, 5.0],
                [0.0, 0.0, 0.0],
            ]
        )
        assert LocalMaxima2DNode().execute(data) == [(1, 1), (1, 2)]

    def test_multiple_separated_peaks(self) -> None:
        # Two well-separated peaks. A small positive threshold filters out the
        # flat-zero background regions far from any peak (which would otherwise
        # all be reported under ``data == maximum_filter(data)``).
        data = np.array(
            [
                [5.0, 1.0, 0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 7.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ]
        )
        assert LocalMaxima2DNode().execute(data, threshold=0.5) == [(0, 0), (3, 4)]

    def test_scalar_threshold(self) -> None:
        # Two peaks with values 3 and 7. Threshold 5 keeps only the 7-peak.
        data = np.array(
            [
                [3.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 7.0],
            ]
        )
        assert LocalMaxima2DNode().execute(data, threshold=5.0) == [(2, 2)]

    def test_array_threshold_per_position(self) -> None:
        data = np.array(
            [
                [3.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 7.0],
            ]
        )
        # Threshold rejects the 3-peak and filters the background-zero plateau on
        # the right edge; only the 7-peak remains.
        threshold = np.full_like(data, 0.5)
        threshold[0, 0] = 5.0
        assert LocalMaxima2DNode().execute(data, threshold=threshold) == [(2, 2)]

    def test_rejects_non_2d_input(self) -> None:
        with pytest.raises(ValueError, match="2D array"):
            LocalMaxima2DNode().execute(np.zeros(5))
        with pytest.raises(ValueError, match="2D array"):
            LocalMaxima2DNode().execute(np.zeros((2, 2, 2)))

    def test_rejects_mismatched_threshold(self) -> None:
        data = np.zeros((3, 3))
        with pytest.raises(ValueError, match=r"scalar or a 2D array of shape \(3, 3\)"):
            LocalMaxima2DNode().execute(data, threshold=np.zeros((2, 3)))

    def test_result_order_is_row_major(self) -> None:
        # Three well-separated peaks placed so that value-sort and column-major sort
        # would each produce a different order than row-major. Locks in the iteration
        # contract. ``threshold=0.5`` filters the flat-zero background regions.
        data = np.array(
            [
                [0.0, 0.0, 0.0, 0.0, 8.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 5.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 6.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ]
        )
        assert LocalMaxima2DNode().execute(data, threshold=0.5) == [(0, 4), (2, 1), (3, 3)]

    def test_array_threshold_mixed_accept_reject(self) -> None:
        # Three well-separated corner/centre peaks at (0,0)=4, (2,2)=8, (4,4)=6.
        # The background uses threshold 0.5 to filter the flat-zero regions
        # (otherwise they'd all pass ``data == maximum_filter(data)``).
        # Per-position overrides:
        #   (0,0): threshold 5.0 > 4.0  -> rejected
        #   (2,2): threshold 1.0 << 8.0 -> kept (comfortable)
        #   (4,4): threshold 6.0 == 6.0 -> kept (``data >= threshold`` accepts equality;
        #                                       mirrors the 1D
        #                                       ``test_scalar_threshold_accepts_equality``).
        data = np.array(
            [
                [4.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 8.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 6.0],
            ]
        )
        threshold = np.full_like(data, 0.5)
        threshold[0, 0] = 5.0
        threshold[2, 2] = 1.0
        threshold[4, 4] = 6.0
        assert LocalMaxima2DNode().execute(data, threshold=threshold) == [(2, 2), (4, 4)]

    def test_radii_asymmetric_wider_axis1(self) -> None:
        # Two peaks of distinct value at cols 1 and 3 along axis 1. With ``radii=(1, 1)``
        # the windows don't overlap so both qualify. With ``radii=(1, 2)`` the
        # axis-1 window from col 1 now reaches col 3 — the smaller peak loses.
        data = np.zeros((1, 5))
        data[0, 1] = 4.0
        data[0, 3] = 5.0
        assert LocalMaxima2DNode(radii=(1, 1)).execute(data) == [(0, 1), (0, 3)]
        assert LocalMaxima2DNode(radii=(1, 2)).execute(data) == [(0, 3)]

    def test_radii_2_2_suppresses_close_peaks(self) -> None:
        # Two distinct peaks at (1, 1)=4 and (3, 3)=7. With radii=(1, 1) both are
        # local maxima. With radii=(2, 2) the window from (3, 3) reaches (1, 1),
        # but (1, 1)=4 < 7 so it loses; only (3, 3) survives. ``threshold=0.5``
        # filters the flat-zero corner cells whose windows contain no peak.
        data = np.zeros((5, 5))
        data[1, 1] = 4.0
        data[3, 3] = 7.0
        assert LocalMaxima2DNode(radii=(1, 1)).execute(data, threshold=0.5) == [(1, 1), (3, 3)]
        assert LocalMaxima2DNode(radii=(2, 2)).execute(data, threshold=0.5) == [(3, 3)]

    def test_radii_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="radii entries must each be at least 1"):
            LocalMaxima2DNode(radii=(0, 1))
        with pytest.raises(ValueError, match="radii entries must each be at least 1"):
            LocalMaxima2DNode(radii=(1, 0))
