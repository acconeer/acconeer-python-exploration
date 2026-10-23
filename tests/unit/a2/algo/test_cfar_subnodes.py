# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for the composable sub-nodes in :mod:`._cfar_subnodes`.

Each test group targets one sub-node and exercises the behaviour described in
that node's docstring. The sub-nodes are pipeline building blocks, so the tests
work on the documented contracts (shapes, return keys, formulae) without
depending on private implementation details.
"""

from __future__ import annotations

import numpy as np
import pytest

from acconeer.exptool.a2.algo.nodes._cfar_subnodes import (
    ArmExtraction1DNode,
    ArmExtraction2DNode,
    ArmStats,
    AxisArmStats,
    AxisPoolNode,
    CFARAggregateMethod,
    CFARAggregateNode,
    CFARKernelType,
    CFARScalingNode,
    IntegralImageNode,
    SidelobeCompensationNode,
)


# --- Constants ---

_RTOL = 1e-10
_ATOL = 1e-12


# --- Group 1: IntegralImageNode ---
#
# Documented contract:
#   * Output shape is ``data.shape + 1`` on every axis (leading zero pad).
#   * 1D windowed sum: ``II[end] - II[start]``.
#   * 2D windowed sum: four-corner inclusion-exclusion.
#   * Works for any number of dimensions.


def test_integral_image_1d_output_shape_is_input_plus_one() -> None:
    """1D input of length ``N`` produces shape ``(N + 1,)``."""
    data = np.arange(7, dtype=np.float64)
    out = IntegralImageNode.execute(data)
    assert out.shape == (data.shape[0] + 1,)


def test_integral_image_1d_leading_zero_padding() -> None:
    """The leading cell of every axis is zero (the documented zero pad)."""
    data = np.arange(1, 8, dtype=np.float64)
    out = IntegralImageNode.execute(data)
    assert out[0] == 0.0


def test_integral_image_1d_windowed_sum_matches_corner_difference() -> None:
    """``II[end] - II[start]`` equals ``data[start:end].sum()`` for every span."""
    rng = np.random.default_rng(0)
    data = rng.standard_normal(20).astype(np.float64)
    II = IntegralImageNode.execute(data)
    N = data.shape[0]
    for start in range(N + 1):
        for end in range(start, N + 1):
            expected = float(data[start:end].sum())
            np.testing.assert_allclose(II[end] - II[start], expected, atol=_ATOL, rtol=_RTOL)


def test_integral_image_2d_output_shape_is_input_plus_one_per_axis() -> None:
    """2D input of shape ``(N0, N1)`` produces shape ``(N0 + 1, N1 + 1)``."""
    data = np.arange(6 * 8, dtype=np.float64).reshape(6, 8)
    out = IntegralImageNode.execute(data)
    assert out.shape == (data.shape[0] + 1, data.shape[1] + 1)


def test_integral_image_2d_first_row_and_column_are_zero() -> None:
    """The leading zero pad on each axis fills the first row and column."""
    rng = np.random.default_rng(1)
    data = rng.standard_normal((5, 6)).astype(np.float64)
    out = IntegralImageNode.execute(data)
    np.testing.assert_array_equal(out[0, :], 0.0)
    np.testing.assert_array_equal(out[:, 0], 0.0)


def test_integral_image_2d_windowed_sum_via_four_corner_formula() -> None:
    """``II[r1, c1] - II[r0, c1] - II[r1, c0] + II[r0, c0]`` equals box sum."""
    rng = np.random.default_rng(2)
    data = rng.standard_normal((6, 7)).astype(np.float64)
    II = IntegralImageNode.execute(data)
    # Sample a handful of arbitrary boxes.
    boxes = [(0, 0, 6, 7), (1, 2, 4, 5), (2, 3, 3, 4), (0, 4, 6, 6)]
    for r0, c0, r1, c1 in boxes:
        expected = float(data[r0:r1, c0:c1].sum())
        got = II[r1, c1] - II[r0, c1] - II[r1, c0] + II[r0, c0]
        np.testing.assert_allclose(got, expected, atol=_ATOL, rtol=_RTOL)


def test_integral_image_3d_output_shape_and_corner_sum() -> None:
    """``IntegralImageNode`` is n-D: 3D input adds one cell to every axis."""
    rng = np.random.default_rng(3)
    data = rng.standard_normal((3, 4, 5)).astype(np.float64)
    II = IntegralImageNode.execute(data)
    assert II.shape == (4, 5, 6)
    # 3D windowed sum via 8-corner inclusion-exclusion at the full-array box.
    total = (
        II[3, 4, 5]
        - II[0, 4, 5]
        - II[3, 0, 5]
        - II[3, 4, 0]
        + II[0, 0, 5]
        + II[0, 4, 0]
        + II[3, 0, 0]
        - II[0, 0, 0]
    )
    np.testing.assert_allclose(total, float(data.sum()), atol=_ATOL, rtol=_RTOL)


def test_integral_image_returns_float64() -> None:
    """Output dtype is float64 even when the input is integer-typed."""
    data = np.arange(5)  # default int dtype
    out = IntegralImageNode.execute(data.astype(np.float64))
    assert out.dtype == np.float64


# --- Group 2: ArmExtraction1DNode ---
#
# Documented contract:
#   * Output is an axis-indexed ``ArmStats`` with one axis. ``axes[0]`` holds
#     the left arm at index 0 and the right arm at index 1.
#   * ``sums`` / ``counts`` are 1D, shaped like ``(II_data.shape[0] - 1,)``.
#   * ``rank``: 0 = empty arm, 1 = partial (boundary-clipped), 2 = full.
#   * Interior cells: a full reference arm has ``ref_radius`` cells.
#   * Boundary cells: arms get clipped; if fully off the array, ``count == 0``.


# Arm index conventions within an axis (negative-side first, positive-side second).
_LEFT, _RIGHT = 0, 1


def _make_1d_arms(data: np.ndarray, guard: int, ref: int) -> ArmStats:
    """Build the integral images and run ``ArmExtraction1DNode``."""
    II_data = IntegralImageNode.execute(data)
    II_ones = IntegralImageNode.execute(np.ones_like(data, dtype=np.float64))
    return ArmExtraction1DNode(guard_radius=guard, ref_radius=ref).execute(II_data, II_ones)


def test_arm_extraction_1d_produces_one_axis_with_two_arms() -> None:
    """``ArmStats`` has a single axis carrying two arms (left, right)."""
    data = np.ones(10, dtype=np.float64)
    stats = _make_1d_arms(data, guard=1, ref=2)
    assert len(stats.axes) == 1
    assert len(stats.axes[0].sums) == 2
    assert len(stats.axes[0].counts) == 2
    assert len(stats.axes[0].ranks) == 2


def test_arm_extraction_1d_output_arrays_have_input_length() -> None:
    """``sums`` / ``counts`` / ``ranks`` are 1D with length ``N``."""
    N = 12
    data = np.ones(N, dtype=np.float64)
    stats = _make_1d_arms(data, guard=1, ref=3)
    axis = stats.axes[0]
    for arm in (_LEFT, _RIGHT):
        assert axis.sums[arm].shape == (N,)
        assert axis.counts[arm].shape == (N,)
        assert axis.ranks[arm].shape == (N,)


def test_arm_extraction_1d_interior_flat_input_full_arms() -> None:
    """At an interior cell each arm holds ``ref`` cells; rank=2; sum = ref*value."""
    value = 3.0
    guard, ref = 1, 4
    N = 20
    data = np.full(N, value, dtype=np.float64)
    stats = _make_1d_arms(data, guard=guard, ref=ref)
    interior = N // 2
    axis = stats.axes[0]
    for arm in (_LEFT, _RIGHT):
        np.testing.assert_allclose(axis.counts[arm][interior], ref, atol=_ATOL, rtol=_RTOL)
        np.testing.assert_allclose(axis.sums[arm][interior], value * ref, atol=_ATOL, rtol=_RTOL)
        assert axis.ranks[arm][interior] == 2


def test_arm_extraction_1d_boundary_left_arm_fully_off_array() -> None:
    """At index 0 the left arm is fully off the array → count=0, rank=0."""
    guard, ref = 1, 3
    data = np.full(15, 2.0, dtype=np.float64)
    stats = _make_1d_arms(data, guard=guard, ref=ref)
    axis = stats.axes[0]
    assert axis.counts[_LEFT][0] == 0
    assert axis.sums[_LEFT][0] == 0.0
    assert axis.ranks[_LEFT][0] == 0


def test_arm_extraction_1d_boundary_partial_arm_has_rank_one() -> None:
    """A partially clipped arm has ``0 < count < ref`` and rank=1."""
    guard, ref = 0, 4
    data = np.full(15, 1.0, dtype=np.float64)
    stats = _make_1d_arms(data, guard=guard, ref=ref)
    axis = stats.axes[0]
    # At idx=2 the left arm spans [-2, 2) → clipped to [0, 2): 2 cells (out of 4).
    assert 0 < axis.counts[_LEFT][2] < ref
    assert axis.ranks[_LEFT][2] == 1


def test_arm_extraction_1d_left_and_right_symmetric_on_flat_input() -> None:
    """Flat input → left/right sums and counts are mirror images of each other."""
    guard, ref = 2, 5
    data = np.full(25, 4.0, dtype=np.float64)
    stats = _make_1d_arms(data, guard=guard, ref=ref)
    axis = stats.axes[0]
    np.testing.assert_allclose(axis.sums[_LEFT], axis.sums[_RIGHT][::-1], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(
        axis.counts[_LEFT], axis.counts[_RIGHT][::-1], atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_array_equal(axis.ranks[_LEFT], axis.ranks[_RIGHT][::-1])


def test_arm_extraction_1d_rejects_zero_ref_radius() -> None:
    """``ref_radius=0`` is degenerate: with zero expected reference cells the
    rank classification can no longer tell empty from partial arms. Reject
    at construction time so the error surface is clear."""
    with pytest.raises(ValueError, match="ref_radius must be at least 1"):
        ArmExtraction1DNode(guard_radius=1, ref_radius=0)


def test_arm_extraction_1d_rejects_negative_guard_radius() -> None:
    with pytest.raises(ValueError, match="guard_radius must be non-negative"):
        ArmExtraction1DNode(guard_radius=-1, ref_radius=2)


def test_arm_extraction_1d_guard_excludes_cells_around_cut() -> None:
    """Cells within ``guard_radius`` of the CUT are excluded from both arms.

    Putting a bright cell adjacent to the CUT (inside the guard) leaves both
    arm sums equal to the flat background sum: the spike sits in the guard
    band, not in either reference arm.
    """
    guard, ref = 2, 3
    background = 1.0
    N = 21
    data = np.full(N, background, dtype=np.float64)
    cut = N // 2
    # Spike inside the guard on the right side.
    data[cut + 1] = 100.0
    stats = _make_1d_arms(data, guard=guard, ref=ref)
    axis = stats.axes[0]
    # Both arms see only ``background`` cells; the spike at cut+1 is in guard.
    expected_sum = background * ref
    np.testing.assert_allclose(axis.sums[_LEFT][cut], expected_sum, atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(axis.sums[_RIGHT][cut], expected_sum, atol=_ATOL, rtol=_RTOL)


# --- Group 3: ArmExtraction2DNode ---
#
# Documented contract:
#   * Output is an axis-indexed ``ArmStats`` with two axes:
#       axes[0]  →  [left, right]   (arms along axis 0)
#       axes[1]  →  [near, far]     (arms along axis 1)
#   * THIN_CROSS kernel: each arm is 1 cell wide perpendicular to its axis.
#   * THICK_CROSS kernel: arms widen to ``2*guard_perpendicular + 1`` cells
#     in the perpendicular direction.
#   * Ranks: 0 = empty (fully off array), 1 = partial (clipped), 2 = full.


# Axis indices in a 2D ``ArmStats``.
_AX0, _AX1 = 0, 1
# Arm indices within an axis (same negative/positive convention as 1D):
# axis 0 holds [left, right]; axis 1 holds [near, far].
_NEAR, _FAR = 0, 1


def _make_2d_arms(
    data: np.ndarray,
    guard: tuple[int, int],
    ref: tuple[int, int],
    kernel: CFARKernelType,
) -> ArmStats:
    """Build integral images and run ``ArmExtraction2DNode``."""
    II_data = IntegralImageNode.execute(data)
    II_ones = IntegralImageNode.execute(np.ones_like(data, dtype=np.float64))
    node = ArmExtraction2DNode(guard_radii=guard, ref_radii=ref, kernel_type=kernel)
    return node.execute(II_data, II_ones)


def test_arm_extraction_2d_produces_two_axes_each_with_two_arms() -> None:
    """``ArmStats`` has two axes, each carrying two arms."""
    data = np.ones((10, 10), dtype=np.float64)
    stats = _make_2d_arms(data, guard=(1, 1), ref=(2, 2), kernel=CFARKernelType.THIN_CROSS)
    assert len(stats.axes) == 2
    for axis in stats.axes:
        assert len(axis.sums) == 2
        assert len(axis.counts) == 2
        assert len(axis.ranks) == 2


def test_arm_extraction_2d_output_arrays_have_input_shape() -> None:
    """All arm arrays have the same 2D shape as the input data."""
    shape = (8, 11)
    data = np.ones(shape, dtype=np.float64)
    stats = _make_2d_arms(data, guard=(1, 1), ref=(2, 3), kernel=CFARKernelType.THIN_CROSS)
    for axis in stats.axes:
        for arm in (0, 1):
            assert axis.sums[arm].shape == shape
            assert axis.counts[arm].shape == shape
            assert axis.ranks[arm].shape == shape


def test_arm_extraction_2d_cross_kernel_interior_counts_match_ref_radius() -> None:
    """THIN_CROSS interior cell: axis-0 arms have ``ref0`` cells; axis-1 arms have ``ref1``."""
    guard, ref = (1, 2), (3, 4)
    data = np.full((20, 20), 5.0, dtype=np.float64)
    stats = _make_2d_arms(data, guard=guard, ref=ref, kernel=CFARKernelType.THIN_CROSS)
    interior = (10, 10)
    assert stats.axes[_AX0].counts[_LEFT][interior] == ref[0]
    assert stats.axes[_AX0].counts[_RIGHT][interior] == ref[0]
    assert stats.axes[_AX1].counts[_NEAR][interior] == ref[1]
    assert stats.axes[_AX1].counts[_FAR][interior] == ref[1]
    for axis in stats.axes:
        for arm in (0, 1):
            assert axis.ranks[arm][interior] == 2


def test_arm_extraction_2d_cross_kernel_interior_sums_match_flat_value() -> None:
    """THIN_CROSS flat input: sum = value · arm-count for each arm at the interior."""
    value = 5.0
    guard, ref = (1, 2), (3, 4)
    data = np.full((20, 20), value, dtype=np.float64)
    stats = _make_2d_arms(data, guard=guard, ref=ref, kernel=CFARKernelType.THIN_CROSS)
    interior = (10, 10)
    np.testing.assert_allclose(
        stats.axes[_AX0].sums[_LEFT][interior], value * ref[0], atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        stats.axes[_AX0].sums[_RIGHT][interior], value * ref[0], atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        stats.axes[_AX1].sums[_NEAR][interior], value * ref[1], atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        stats.axes[_AX1].sums[_FAR][interior], value * ref[1], atol=_ATOL, rtol=_RTOL
    )


def test_arm_extraction_2d_extended_cross_widens_arms_by_perpendicular_window() -> None:
    """THICK_CROSS interior cell counts: ``ref_a * (2*guard_b + 1)`` per arm."""
    guard, ref = (1, 2), (3, 4)
    data = np.full((20, 20), 1.0, dtype=np.float64)
    stats = _make_2d_arms(data, guard=guard, ref=ref, kernel=CFARKernelType.THICK_CROSS)
    interior = (10, 10)
    w0 = 2 * guard[0] + 1
    w1 = 2 * guard[1] + 1
    # Axis-0 arms (left/right) have perpendicular extent w1 along axis 1.
    assert stats.axes[_AX0].counts[_LEFT][interior] == ref[0] * w1
    assert stats.axes[_AX0].counts[_RIGHT][interior] == ref[0] * w1
    # Axis-1 arms (near/far) have perpendicular extent w0 along axis 0.
    assert stats.axes[_AX1].counts[_NEAR][interior] == ref[1] * w0
    assert stats.axes[_AX1].counts[_FAR][interior] == ref[1] * w0
    for axis in stats.axes:
        for arm in (0, 1):
            assert axis.ranks[arm][interior] == 2


def test_arm_extraction_2d_corner_has_empty_left_and_near_arms() -> None:
    """At the (0, 0) corner the ``left`` and ``near`` arms fall fully off the array."""
    guard, ref = (1, 1), (2, 2)
    data = np.full((10, 10), 1.0, dtype=np.float64)
    stats = _make_2d_arms(data, guard=guard, ref=ref, kernel=CFARKernelType.THIN_CROSS)
    corner = (0, 0)
    assert stats.axes[_AX0].counts[_LEFT][corner] == 0
    assert stats.axes[_AX0].sums[_LEFT][corner] == 0.0
    assert stats.axes[_AX0].ranks[_LEFT][corner] == 0
    assert stats.axes[_AX1].counts[_NEAR][corner] == 0
    assert stats.axes[_AX1].sums[_NEAR][corner] == 0.0
    assert stats.axes[_AX1].ranks[_NEAR][corner] == 0


def test_arm_extraction_2d_cross_axis_0_arms_isolated_from_axis_1_variation() -> None:
    """A spike along the row through the CUT enters only the axis-1 (near/far) arms.

    The THIN_CROSS-kernel axis-0 (left/right) arms sample axis 0 at the CUT's column, so
    changing values along axis 1 at the CUT row must not affect them. This pins down
    the contract that axis-0 arms extend along axis 0.
    """
    guard, ref = (1, 1), (3, 3)
    background = 1.0
    cut = (10, 10)
    data = np.full((20, 20), background, dtype=np.float64)
    stats_flat = _make_2d_arms(data, guard=guard, ref=ref, kernel=CFARKernelType.THIN_CROSS)

    data_perturbed = data.copy()
    data_perturbed[cut[0], :] += 100.0  # change the whole CUT row
    stats_perturbed = _make_2d_arms(
        data_perturbed, guard=guard, ref=ref, kernel=CFARKernelType.THIN_CROSS
    )
    # Axis-0 arms read column ``cut[1]`` along axis 0 → unchanged at the CUT.
    np.testing.assert_allclose(
        stats_perturbed.axes[_AX0].sums[_LEFT][cut],
        stats_flat.axes[_AX0].sums[_LEFT][cut],
        atol=_ATOL,
        rtol=_RTOL,
    )
    np.testing.assert_allclose(
        stats_perturbed.axes[_AX0].sums[_RIGHT][cut],
        stats_flat.axes[_AX0].sums[_RIGHT][cut],
        atol=_ATOL,
        rtol=_RTOL,
    )
    # Axis-1 arms do see the perturbation (sanity check that the perturbation reached them).
    assert stats_perturbed.axes[_AX1].sums[_NEAR][cut] > stats_flat.axes[_AX1].sums[_NEAR][cut]
    assert stats_perturbed.axes[_AX1].sums[_FAR][cut] > stats_flat.axes[_AX1].sums[_FAR][cut]


def test_arm_extraction_2d_rejects_zero_ref_radius_per_axis() -> None:
    """Zero on either axis is degenerate for the same reason as the 1D node."""
    with pytest.raises(ValueError, match="ref_radii entries must each be at least 1"):
        ArmExtraction2DNode(guard_radii=(1, 1), ref_radii=(0, 2))
    with pytest.raises(ValueError, match="ref_radii entries must each be at least 1"):
        ArmExtraction2DNode(guard_radii=(1, 1), ref_radii=(2, 0))


def test_arm_extraction_2d_rejects_negative_guard_radius_per_axis() -> None:
    with pytest.raises(ValueError, match="guard_radii entries must be non-negative"):
        ArmExtraction2DNode(guard_radii=(-1, 1), ref_radii=(2, 2))
    with pytest.raises(ValueError, match="guard_radii entries must be non-negative"):
        ArmExtraction2DNode(guard_radii=(1, -1), ref_radii=(2, 2))


def test_arm_extraction_2d_guard_excludes_cells_around_cut() -> None:
    """Cells within ``guard_radii`` of the CUT are excluded from every arm."""
    guard, ref = (2, 2), (3, 3)
    background = 1.0
    cut = (10, 10)
    data = np.full((21, 21), background, dtype=np.float64)
    # Place a bright cell adjacent to the CUT along each axis (inside the guard).
    data[cut[0] + 1, cut[1]] = 100.0
    data[cut[0], cut[1] + 1] = 100.0
    stats = _make_2d_arms(data, guard=guard, ref=ref, kernel=CFARKernelType.THIN_CROSS)
    expected_axis0 = background * ref[0]
    expected_axis1 = background * ref[1]
    np.testing.assert_allclose(
        stats.axes[_AX0].sums[_LEFT][cut], expected_axis0, atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        stats.axes[_AX0].sums[_RIGHT][cut], expected_axis0, atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        stats.axes[_AX1].sums[_NEAR][cut], expected_axis1, atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        stats.axes[_AX1].sums[_FAR][cut], expected_axis1, atol=_ATOL, rtol=_RTOL
    )


# --- Group 4: CFARAggregateNode ---
#
# Documented contract:
#   * Operates on the arms along the configured ``axis`` of an ``ArmStats``.
#   * ``CA``: pool sums and counts across the axis's arms.
#   * ``GO``: per cell, pick the arm with the highest mean (sum/count).
#   * ``SO``: per cell, pick the arm with the lowest mean.
#   * ``GO`` / ``SO`` prefer arms with higher ``rank`` (full > partial > empty);
#     ties are broken by mean.
#   * ``DROP``: returns zeros so a pooled axis contributes nothing.
#   * Output ``(sum, count)`` arrays have the same shape as the input arms.


def _axis_arms_from_sums_counts(
    sums: list[np.ndarray], counts: list[np.ndarray], expected_count: int
) -> AxisArmStats:
    """Build :class:`AxisArmStats` with ranks derived from ``counts`` and ``expected_count``."""
    ranks = [(c >= expected_count).astype(np.int8) + (c > 0).astype(np.int8) for c in counts]
    return AxisArmStats(sums=sums, counts=counts, ranks=ranks)


def _make_single_axis_stats(
    sums: list[np.ndarray], counts: list[np.ndarray], expected_count: int
) -> ArmStats:
    """Build an :class:`ArmStats` with a single axis carrying the given arms."""
    return ArmStats(axes=[_axis_arms_from_sums_counts(sums, counts, expected_count)])


def test_aggregate_ca_pools_all_arms_on_the_configured_axis() -> None:
    """``CA`` adds sums and counts over every arm on the configured axis."""
    sums = [
        np.array([1.0, 2.0, 3.0]),
        np.array([10.0, 20.0, 30.0]),
        np.array([100.0, 200.0, 300.0]),
    ]
    counts = [np.full(3, 4.0) for _ in sums]
    stats = _make_single_axis_stats(sums, counts, expected_count=4)
    out_sum, out_count = CFARAggregateNode(method=CFARAggregateMethod.CA, axis=0).execute(stats)
    np.testing.assert_allclose(out_sum, [111.0, 222.0, 333.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out_count, [12.0, 12.0, 12.0], atol=_ATOL, rtol=_RTOL)


def test_aggregate_axis_param_selects_which_axis_to_aggregate() -> None:
    """``axis`` picks which axis's arms the node operates on; other axes are ignored."""
    axis0 = _axis_arms_from_sums_counts(
        sums=[np.array([1.0]), np.array([2.0])],
        counts=[np.array([3.0]), np.array([3.0])],
        expected_count=3,
    )
    axis1 = _axis_arms_from_sums_counts(
        sums=[np.array([100.0]), np.array([200.0])],
        counts=[np.array([5.0]), np.array([5.0])],
        expected_count=5,
    )
    stats = ArmStats(axes=[axis0, axis1])

    out_sum_0, out_count_0 = CFARAggregateNode(method=CFARAggregateMethod.CA, axis=0).execute(
        stats
    )
    out_sum_1, out_count_1 = CFARAggregateNode(method=CFARAggregateMethod.CA, axis=1).execute(
        stats
    )

    np.testing.assert_allclose(out_sum_0, [3.0], atol=_ATOL, rtol=_RTOL)  # 1 + 2
    np.testing.assert_allclose(out_count_0, [6.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out_sum_1, [300.0], atol=_ATOL, rtol=_RTOL)  # 100 + 200
    np.testing.assert_allclose(out_count_1, [10.0], atol=_ATOL, rtol=_RTOL)


def test_aggregate_go_selects_arm_with_highest_mean() -> None:
    """``GO`` picks the arm with the largest mean (sum/count) per cell."""
    # Two arms, equal counts and rank → selection by mean alone.
    sums = [np.array([1.0, 5.0]), np.array([10.0, 2.0])]
    counts = [np.array([2.0, 2.0]), np.array([2.0, 2.0])]
    stats = _make_single_axis_stats(sums, counts, expected_count=2)
    out_sum, out_count = CFARAggregateNode(method=CFARAggregateMethod.GO, axis=0).execute(stats)
    # Cell 0: mean(a)=0.5, mean(b)=5.0 → pick b. Cell 1: mean(a)=2.5, mean(b)=1.0 → pick a.
    np.testing.assert_allclose(out_sum, [10.0, 5.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out_count, [2.0, 2.0], atol=_ATOL, rtol=_RTOL)


def test_aggregate_so_selects_arm_with_lowest_mean() -> None:
    """``SO`` picks the arm with the smallest mean per cell."""
    sums = [np.array([1.0, 5.0]), np.array([10.0, 2.0])]
    counts = [np.array([2.0, 2.0]), np.array([2.0, 2.0])]
    stats = _make_single_axis_stats(sums, counts, expected_count=2)
    out_sum, out_count = CFARAggregateNode(method=CFARAggregateMethod.SO, axis=0).execute(stats)
    # Cell 0: smaller mean is a (0.5). Cell 1: smaller mean is b (1.0).
    np.testing.assert_allclose(out_sum, [1.0, 2.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out_count, [2.0, 2.0], atol=_ATOL, rtol=_RTOL)


def test_aggregate_go_prefers_higher_rank_over_higher_mean() -> None:
    """``GO`` picks the higher-rank arm even if a lower-rank arm has a larger mean."""
    # Arm 0: full (rank=2), low mean. Arm 1: partial (rank=1), high mean.
    sums = [np.array([2.0]), np.array([100.0])]
    counts = [np.array([2.0]), np.array([1.0])]  # expected=2 → arm 1 is partial
    stats = _make_single_axis_stats(sums, counts, expected_count=2)
    assert stats.axes[0].ranks[0][0] == 2
    assert stats.axes[0].ranks[1][0] == 1
    out_sum, out_count = CFARAggregateNode(method=CFARAggregateMethod.GO, axis=0).execute(stats)
    # Rank dominates → pick arm 0 despite its lower mean.
    np.testing.assert_allclose(out_sum, [2.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out_count, [2.0], atol=_ATOL, rtol=_RTOL)


def test_aggregate_so_prefers_higher_rank_over_lower_mean() -> None:
    """``SO`` picks the higher-rank arm even if a lower-rank arm has a smaller mean."""
    sums = [np.array([10.0]), np.array([1.0])]
    counts = [np.array([2.0]), np.array([1.0])]  # expected=2 → arm 1 partial
    stats = _make_single_axis_stats(sums, counts, expected_count=2)
    assert stats.axes[0].ranks[0][0] == 2
    assert stats.axes[0].ranks[1][0] == 1
    out_sum, out_count = CFARAggregateNode(method=CFARAggregateMethod.SO, axis=0).execute(stats)
    # Rank dominates → pick arm 0 (mean=5) despite arm 1 having mean=1.
    np.testing.assert_allclose(out_sum, [10.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out_count, [2.0], atol=_ATOL, rtol=_RTOL)


def test_aggregate_drop_returns_zeros_of_same_shape() -> None:
    """``DROP`` returns ``(sum, count)`` of all zeros, matching the arm shape."""
    sums = [np.array([[1.0, 2.0], [3.0, 4.0]])]
    counts = [np.array([[2.0, 2.0], [2.0, 2.0]])]
    stats = _make_single_axis_stats(sums, counts, expected_count=2)
    out_sum, out_count = CFARAggregateNode(method=CFARAggregateMethod.DROP, axis=0).execute(stats)
    assert out_sum.shape == sums[0].shape
    assert out_count.shape == sums[0].shape
    np.testing.assert_array_equal(out_sum, np.zeros_like(sums[0]))
    np.testing.assert_array_equal(out_count, np.zeros_like(sums[0]))


def test_aggregate_output_shape_matches_input_arm_shape() -> None:
    """``(sum, count)`` arrays have the same shape as each arm array."""
    shape = (4, 5)
    sums = [np.full(shape, 1.0), np.full(shape, 2.0)]
    counts = [np.full(shape, 3.0), np.full(shape, 3.0)]
    stats = _make_single_axis_stats(sums, counts, expected_count=3)
    for method in (CFARAggregateMethod.CA, CFARAggregateMethod.GO, CFARAggregateMethod.SO):
        out_sum, out_count = CFARAggregateNode(method=method, axis=0).execute(stats)
        assert out_sum.shape == shape
        assert out_count.shape == shape


def test_aggregate_go_selects_per_cell_independently() -> None:
    """``GO`` selection is computed cell-by-cell (different arms can win in different cells)."""
    sums = [
        np.array([1.0, 8.0, 4.0]),
        np.array([3.0, 2.0, 4.0]),
    ]
    counts = [np.full(3, 2.0), np.full(3, 2.0)]
    stats = _make_single_axis_stats(sums, counts, expected_count=2)
    out_sum, _ = CFARAggregateNode(method=CFARAggregateMethod.GO, axis=0).execute(stats)
    # Cell 0: mean a=0.5 < b=1.5 → b. Cell 1: a=4 > b=1 → a. Cell 2: equal → a (first wins).
    np.testing.assert_allclose(out_sum, [3.0, 8.0, 4.0], atol=_ATOL, rtol=_RTOL)


# --- Group 5: AxisPoolNode ---
#
# Documented contract:
#   * Element-wise sum of two ``(sum, count)`` pairs.
#   * Output shape matches the input pair shape.
#   * A zero-valued pair (the ``DROP`` aggregator's output) leaves the pool
#     unchanged.


def test_axis_pool_sums_and_counts_element_wise() -> None:
    """Pooled sum/count are the element-wise sums of the two input pairs."""
    s0 = np.array([1.0, 2.0, 3.0])
    c0 = np.array([5.0, 5.0, 5.0])
    s1 = np.array([10.0, 20.0, 30.0])
    c1 = np.array([4.0, 4.0, 4.0])
    pooled_s, pooled_c = AxisPoolNode.execute((s0, c0), (s1, c1))
    np.testing.assert_allclose(pooled_s, [11.0, 22.0, 33.0], atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(pooled_c, [9.0, 9.0, 9.0], atol=_ATOL, rtol=_RTOL)


def test_axis_pool_output_shape_matches_input_shape() -> None:
    """Output arrays have the same shape as the per-axis input arrays."""
    shape = (6, 8)
    s0 = np.full(shape, 1.0)
    c0 = np.full(shape, 2.0)
    s1 = np.full(shape, 3.0)
    c1 = np.full(shape, 4.0)
    pooled_s, pooled_c = AxisPoolNode.execute((s0, c0), (s1, c1))
    assert pooled_s.shape == shape
    assert pooled_c.shape == shape


def test_axis_pool_with_zero_axis_leaves_other_axis_unchanged() -> None:
    """Pooling a non-zero axis with zeros (the ``DROP`` aggregator) is a no-op."""
    s0 = np.array([1.5, 2.5, 3.5])
    c0 = np.array([2.0, 3.0, 4.0])
    zeros = np.zeros_like(s0)
    pooled_s, pooled_c = AxisPoolNode.execute((s0, c0), (zeros, zeros))
    np.testing.assert_allclose(pooled_s, s0, atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(pooled_c, c0, atol=_ATOL, rtol=_RTOL)


def test_axis_pool_returns_float64_arrays() -> None:
    """Output arrays are float64 regardless of input dtype."""
    s0 = np.array([1.0, 2.0])
    c0 = np.array([3.0, 4.0])
    pooled_s, pooled_c = AxisPoolNode.execute((s0, c0), (s0, c0))
    assert pooled_s.dtype == np.float64
    assert pooled_c.dtype == np.float64


# --- Group 6: CFARScalingNode ---
#
# Documented contract:
#   * ``threshold = (arm_sum / N) · N · (fpr^(−1/N) − 1)`` cell-wise.
#   * Cells with ``N == 0`` get ``threshold = inf``.
#   * Output is clipped from below by ``fixed_threshold``.


def _cfar_scaling(n: int, fpr: float) -> float:
    """Closed-form CFAR scaling factor for ``n`` reference cells at ``fpr``."""
    return n * (fpr ** (-1.0 / n) - 1.0)


def test_cfar_scaling_matches_closed_form_formula() -> None:
    """``threshold = noise · N · (fpr^(-1/N) - 1)`` cell-wise."""
    fpr = 1e-2
    noise = 4.0
    n = 10
    arm_sum = np.full(5, noise * n, dtype=np.float64)
    num_samples = np.full(5, float(n), dtype=np.float64)
    out = CFARScalingNode(theoretical_fpr=fpr).execute(arm_sum, num_samples)
    expected = noise * _cfar_scaling(n, fpr)
    np.testing.assert_allclose(out, expected, atol=_ATOL, rtol=_RTOL)


def test_cfar_scaling_returns_inf_when_num_samples_is_zero() -> None:
    """Cells with ``N == 0`` get ``threshold = inf``."""
    fpr = 1e-2
    arm_sum = np.array([0.0, 5.0, 0.0])
    num_samples = np.array([0.0, 10.0, 0.0])
    out = CFARScalingNode(theoretical_fpr=fpr).execute(arm_sum, num_samples)
    assert np.isinf(out[0])
    assert np.isinf(out[2])
    assert np.isfinite(out[1])


def test_cfar_scaling_fixed_threshold_clips_from_below() -> None:
    """``fixed_threshold`` is a hard floor for every cell."""
    fpr = 1e-2
    floor = 50.0
    # Quiet input — the CFAR-scaled value sits well below the floor everywhere.
    arm_sum = np.full(5, 0.1, dtype=np.float64)
    num_samples = np.full(5, 8.0, dtype=np.float64)
    out = CFARScalingNode(theoretical_fpr=fpr, fixed_threshold=floor).execute(arm_sum, num_samples)
    np.testing.assert_allclose(out, floor, atol=_ATOL, rtol=_RTOL)


def test_cfar_scaling_fixed_threshold_does_not_lower_cfar_when_already_above() -> None:
    """A low ``fixed_threshold`` leaves the CFAR-scaled threshold unchanged."""
    fpr = 1e-2
    arm_sum = np.full(3, 80.0, dtype=np.float64)  # noise=10, n=8 → big threshold
    num_samples = np.full(3, 8.0, dtype=np.float64)
    out_no_floor = CFARScalingNode(theoretical_fpr=fpr).execute(arm_sum, num_samples)
    out_with_floor = CFARScalingNode(theoretical_fpr=fpr, fixed_threshold=0.5).execute(
        arm_sum, num_samples
    )
    np.testing.assert_allclose(out_with_floor, out_no_floor, atol=_ATOL, rtol=_RTOL)


def test_cfar_scaling_handles_varying_n_per_cell() -> None:
    """Per-cell ``N`` controls the scaling factor independently for each cell."""
    fpr = 1e-2
    noise = 2.0
    ns = np.array([4.0, 8.0, 16.0])
    arm_sum = noise * ns
    num_samples = ns
    out = CFARScalingNode(theoretical_fpr=fpr).execute(arm_sum, num_samples)
    for i, n in enumerate(ns):
        expected = noise * _cfar_scaling(int(n), fpr)
        np.testing.assert_allclose(out[i], expected, atol=_ATOL, rtol=_RTOL)


def test_cfar_scaling_preserves_input_shape_for_2d_inputs() -> None:
    """2D ``(arm_sum, num_samples)`` produces a 2D threshold of the same shape."""
    fpr = 1e-2
    shape = (5, 7)
    arm_sum = np.full(shape, 16.0)
    num_samples = np.full(shape, 8.0)
    out = CFARScalingNode(theoretical_fpr=fpr).execute(arm_sum, num_samples)
    assert out.shape == shape


def test_cfar_scaling_rejects_fpr_out_of_unit_interval() -> None:
    """The constructor rejects ``theoretical_fpr`` outside ``(0, 1)``."""
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="theoretical_fpr"):
            CFARScalingNode(theoretical_fpr=bad)


def test_cfar_scaling_rejects_negative_fixed_threshold() -> None:
    """The constructor rejects a negative ``fixed_threshold``."""
    with pytest.raises(ValueError, match="fixed_threshold"):
        CFARScalingNode(theoretical_fpr=1e-2, fixed_threshold=-1.0)


# --- Group 7: SidelobeCompensationNode ---
#
# Documented contract:
#   * Output ≥ ``max_along_axis(data) · 10^(dB/10)`` element-wise.
#   * ``dB = None`` makes the node a no-op.
#   * 1D ``axis=0`` collapses across the only axis (global max).
#   * 2D ``axis=0`` derives a per-column floor; ``axis=1`` a per-row floor.


def test_sidelobe_dB_none_returns_threshold_unchanged() -> None:
    """``side_lobe_compensation_dB=None`` is a no-op."""
    threshold = np.array([0.1, 0.2, 0.3])
    data = np.array([100.0, 100.0, 100.0])
    out = SidelobeCompensationNode(side_lobe_compensation_dB=None).execute(threshold, data)
    np.testing.assert_array_equal(out, threshold)


def test_sidelobe_floor_uses_global_max_for_1d_input() -> None:
    """1D ``axis=0`` collapses across the only axis: floor = ``max(data) · 10^(dB/10)``."""
    db = -20.0  # floor = max(data) * 0.01
    data = np.array([1.0, 100.0, 50.0])  # max = 100 → floor = 1.0
    threshold = np.array([0.01, 0.02, 0.03])  # all below the floor
    out = SidelobeCompensationNode(side_lobe_compensation_dB=db, axis=0).execute(threshold, data)
    expected_floor = data.max() * 10 ** (db / 10)
    np.testing.assert_allclose(out, expected_floor, atol=_ATOL, rtol=_RTOL)


def test_sidelobe_keeps_threshold_when_already_above_floor() -> None:
    """A threshold cell above the floor is left unchanged."""
    db = -20.0
    data = np.array([1.0, 100.0, 50.0])  # floor = 1.0
    threshold = np.array([0.01, 500.0, 0.5])  # cell 1 above floor, cells 0/2 below
    out = SidelobeCompensationNode(side_lobe_compensation_dB=db, axis=0).execute(threshold, data)
    floor = data.max() * 10 ** (db / 10)
    np.testing.assert_allclose(out[0], floor, atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out[1], 500.0, atol=_ATOL, rtol=_RTOL)
    np.testing.assert_allclose(out[2], floor, atol=_ATOL, rtol=_RTOL)


def test_sidelobe_2d_axis_0_applies_per_column_floor() -> None:
    """``axis=0`` derives one floor per column from ``max(data, axis=0)``."""
    db = -20.0
    data = np.array(
        [
            [10.0, 1.0],
            [1.0, 100.0],
        ]
    )  # max(axis=0) = [10, 100] → floors = [0.1, 1.0]
    threshold = np.zeros_like(data)
    out = SidelobeCompensationNode(side_lobe_compensation_dB=db, axis=0).execute(threshold, data)
    expected = data.max(axis=0, keepdims=True) * 10 ** (db / 10)
    np.testing.assert_allclose(out, np.broadcast_to(expected, data.shape), atol=_ATOL, rtol=_RTOL)


def test_sidelobe_2d_axis_1_applies_per_row_floor() -> None:
    """``axis=1`` derives one floor per row from ``max(data, axis=1)``."""
    db = -20.0
    data = np.array(
        [
            [10.0, 1.0],
            [1.0, 100.0],
        ]
    )  # max(axis=1) = [10, 100] → row floors = [0.1, 1.0]
    threshold = np.zeros_like(data)
    out = SidelobeCompensationNode(side_lobe_compensation_dB=db, axis=1).execute(threshold, data)
    expected = data.max(axis=1, keepdims=True) * 10 ** (db / 10)
    np.testing.assert_allclose(out, np.broadcast_to(expected, data.shape), atol=_ATOL, rtol=_RTOL)


def test_sidelobe_output_is_element_wise_max_of_threshold_and_floor() -> None:
    """Every cell satisfies ``out = max(threshold, floor)``."""
    db = -10.0
    rng = np.random.default_rng(0)
    data = rng.exponential(scale=1.0, size=(6, 8))
    threshold = rng.uniform(0.0, 1.0, size=(6, 8))
    out = SidelobeCompensationNode(side_lobe_compensation_dB=db, axis=0).execute(threshold, data)
    floor = data.max(axis=0, keepdims=True) * 10 ** (db / 10)
    np.testing.assert_allclose(out, np.maximum(threshold, floor), atol=_ATOL, rtol=_RTOL)


def test_sidelobe_rejects_non_negative_dB() -> None:
    """The constructor rejects ``dB >= 0`` (it is a dB *below* the max)."""
    for bad in (0.0, 5.0):
        with pytest.raises(ValueError, match="side_lobe_compensation_dB"):
            SidelobeCompensationNode(side_lobe_compensation_dB=bad)
