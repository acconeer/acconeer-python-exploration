# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Composable sub-nodes for CFAR threshold computation.

A CFAR threshold map decomposes into a pipeline of small, single-concern nodes::

    IntegralImageNode(data)                          → II_data
    [IntegralImageNode(np.ones_like(data))]          → II_ones
        ↓
    ArmExtraction1DNode | ArmExtraction2DNode        → ArmStats
        ↓
    CFARAggregateNode(method, axis=…)                    → (sum_array, count_array)
        (instantiate once per axis for 2D; pool results with AxisPoolNode)
        ↓
    CFARScalingNode(fpr, fixed_threshold)            → threshold_map
        ↓
    [SidelobeCompensationNode(dB, axis)]             → threshold_map
        (instantiate once per axis for 2D)

``ArmStats`` is axis-indexed: ``stats.axes[k]`` is an :class:`AxisArmStats`
holding the arms along axis ``k``. The 1D extractor produces one axis; the 2D
extractor produces two. ``CFARAggregateNode`` then operates on one axis at a time.

The convenience wrappers in :mod:`._cfar_nodes` compose these into typical patterns.
"""

from __future__ import annotations

import typing as t
from dataclasses import dataclass
from enum import Enum

import numpy as np
import numpy.typing as npt


_NDf64 = npt.NDArray[np.float64]
_NDint = npt.NDArray[np.intp]
_NDi8 = npt.NDArray[np.int8]


# --- Kernel shape ---


class CFARKernelType(str, Enum):
    """Shape of the 2D-CFAR reference window kernel.

    Both kernels have four arms (left/right along axis 0, near/far along axis 1).
    They differ in how wide each arm is *perpendicular* to its own axis.
    """

    THIN_CROSS = "THIN_CROSS"
    """Thin cross: each arm is 1 cell wide perpendicular to its axis."""
    THICK_CROSS = "THICK_CROSS"
    """Thick cross: each arm widens to ``2 * guard_radii[perpendicular] + 1`` cells
    perpendicular to its axis, spanning the full guard band across the CUT."""


# --- Per-arm statistics ---


@dataclass
class AxisArmStats:
    """Sums / counts / ranks for the arms along one axis of the CFAR window.

    Each list has one entry per arm on this axis (2 for left/right or near/far
    in the current extractors). All numpy arrays share the input map's shape.

    The list ordering is part of the extractor contract: index 0 is the
    negative-side arm (lower indices along the axis), index 1 is the
    positive-side arm.

    ``ranks`` encodes 0 = empty, 1 = partial (boundary-clipped), 2 = full —
    used by GO/SO to prefer full arms over partial ones when picking by mean.
    """

    sums: list[_NDf64]
    counts: list[_NDf64]
    ranks: list[_NDi8]


@dataclass
class ArmStats:
    """Per-axis arm statistics. ``axes[k]`` covers the arms along axis ``k``.

    1D extractors produce one axis (``len(axes) == 1``); 2D extractors produce
    two (``len(axes) == 2``). Sub-nodes downstream operate on one axis at a
    time via :class:`CFARAggregateNode`.
    """

    axes: list[AxisArmStats]


def _ranks_for_axis(counts: list[_NDf64], expected_count: int) -> list[_NDi8]:
    """Compute per-arm rank: 0=empty, 1=partial, 2=full reference window."""
    return [(c >= expected_count).astype(np.int8) + (c > 0).astype(np.int8) for c in counts]


def _axis_arm_means(axis_arms: AxisArmStats) -> list[_NDf64]:
    """Compute per-arm means from sums/counts on a single axis; empty arms get ``inf``."""
    means: list[_NDf64] = []
    for s, c in zip(axis_arms.sums, axis_arms.counts):
        safe_c = np.where(c > 0, c, 1.0)
        m = np.asarray(s / safe_c, dtype=np.float64)
        m[c == 0] = np.inf
        means.append(m)
    return means


# --- Integral image ---


class IntegralImageNode:
    """Generic n-D integral image with a leading zero pad on each axis.

    The output has shape ``data.shape + 1`` on each axis. Windowed sums become
    differences of corner values: for 1D, ``win_sum = II[end] - II[start]``;
    for 2D, the four-corner inclusion-exclusion formula applies.
    """

    @staticmethod
    def execute(data: _NDf64) -> _NDf64:
        """Compute the n-D integral image of ``data``.

        :param data: Input array of shape ``S`` (any number of dimensions).
        :returns: Integral image of shape ``S + 1`` on each axis.
        """
        result = np.asarray(data, dtype=np.float64)
        for axis in range(result.ndim):
            pad_width: list[t.Tuple[int, int]] = [(0, 0)] * result.ndim
            pad_width[axis] = (1, 0)
            result = np.pad(result, pad_width, mode="constant", constant_values=0.0)
            result = np.cumsum(result, axis=axis, dtype=np.float64)
        return np.asarray(result, dtype=np.float64)


# --- Arm extraction ---


class ArmExtraction1DNode:
    """Extract the left and right reference arms from a 1D integral image.

    The produced :class:`ArmStats` has a single axis with two arms in
    ``[negative-side, positive-side]`` order (i.e. ``axes[0].sums[0]`` is the
    left arm, ``axes[0].sums[1]`` is the right arm).

    Window layout around each Cell Under Test (CUT)::

    R = Reference  |  G = Guard  |  C = CUT
            LEFT ARM                                                 RIGHT ARM
    <-- ref_radius --><- guard_radius ->    <- guard_radius -><-- ref_radius -->
    | R R R R R R R R | G G G G G G G G | C | G G G G G G G G | R R R R R R R R |

    Boundary cells get clipped arms (``counts < expected``, ``rank == 1``);
    cells where an arm is fully off the array get ``counts == 0`` and
    ``rank == 0``.
    """

    def __init__(self, guard_radius: int, ref_radius: int):
        """
        :param guard_radius: Width of the guard band (cells excluded from the reference window).
            Must be non-negative.
        :param ref_radius: Width of the reference window on each side of the guard band.
            Must be at least 1; a zero radius would leave the rank classification ambiguous
            (every cell looks "partial" because the expected count is zero).
        """
        if guard_radius < 0:
            msg = f"guard_radius must be non-negative, got {guard_radius}."
            raise ValueError(msg)
        if ref_radius < 1:
            msg = f"ref_radius must be at least 1, got {ref_radius}."
            raise ValueError(msg)
        self._guard_radius = guard_radius
        self._ref_radius = ref_radius

    def execute(self, II_data: _NDf64, II_ones: _NDf64) -> ArmStats:
        """Compute per-arm sums, counts and ranks from a 1D integral image.

        :param II_data: 1D integral image of the data, shape ``(N + 1,)``.
        :param II_ones: 1D integral image of ones (same shape), used to count cells per arm.
        :returns: :class:`ArmStats` with a single axis whose two arms are
            ``[left, right]`` in that order.
        """
        N = II_data.shape[0] - 1
        idx = np.arange(N)
        g, r = self._guard_radius, self._ref_radius

        def clip(v: _NDint) -> _NDint:
            return np.asarray(np.clip(v, 0, N), dtype=np.intp)

        l_start = clip(idx - g - r)
        l_end = clip(idx - g)
        r_start = clip(idx + g + 1)
        r_end = clip(idx + g + r + 1)

        def win(P: _NDf64, i0: _NDint, i1: _NDint) -> _NDf64:
            return np.asarray(P[i1] - P[i0], dtype=np.float64)

        sums = [win(II_data, l_start, l_end), win(II_data, r_start, r_end)]
        counts = [win(II_ones, l_start, l_end), win(II_ones, r_start, r_end)]
        ranks = _ranks_for_axis(counts, expected_count=r)
        return ArmStats(axes=[AxisArmStats(sums=sums, counts=counts, ranks=ranks)])


class ArmExtraction2DNode:
    """Extract the four reference arms from a 2D integral image.

    The produced :class:`ArmStats` has two axes::

        axes[0]  →  AxisArmStats(sums=[left, right],   …)   # arms along axis 0
        axes[1]  →  AxisArmStats(sums=[near, far],     …)   # arms along axis 1

    With ``THIN_CROSS`` kernel each arm is 1 cell wide perpendicular to its axis;
    with ``THICK_CROSS`` arms widen to ``2*guard_perpendicular + 1`` cells.
    Within an axis the order is ``[negative-side, positive-side]``.

    THIN_CROSS kernel layout around each Cell Under Test (CUT)::
        R = Reference  |  G = Guard  |  C = CUT
                                                   _  ^
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  | ref_radii[1]     NEAR ARM
                                                   R  |
                                                   R  |
                                                   R  |
                                                   _  v
                                                   _  ^
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  | guard_radii[1]
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  |
               LEFT ARM                            _  v                              RIGHT ARM
        <--- ref_radii[0] ---><-- guard_radii[0] --->   <-- guard_radii[0] ---><--- ref_radii[0] --->
        | R R R R R R R R R R | G G G G G G G G G G | C | G G G G G G G G G G | R R R R R R R R R R |
                                                   _  ^
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  | guard_radii[1]
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  |
                                                   _  v
                                                   _  ^
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  | ref_radii[1]     FAR ARM
                                                   R  |
                                                   R  |
                                                   R  |
                                                   _  v
    """

    def __init__(
        self,
        guard_radii: t.Tuple[int, int],
        ref_radii: t.Tuple[int, int],
        kernel_type: CFARKernelType = CFARKernelType.THIN_CROSS,
    ):
        """
        :param guard_radii: Guard widths ``(axis0, axis1)`` in cells. Each entry must be
            non-negative.
        :param ref_radii: Reference window widths ``(axis0, axis1)`` in cells. Each entry
            must be at least 1.
        :param kernel_type: Shape of the reference window (``THIN_CROSS`` or ``THICK_CROSS``).
        """
        if any(g < 0 for g in guard_radii):
            msg = f"guard_radii entries must be non-negative, got {guard_radii}."
            raise ValueError(msg)
        if any(r < 1 for r in ref_radii):
            msg = f"ref_radii entries must each be at least 1, got {ref_radii}."
            raise ValueError(msg)
        self._guard_radii = guard_radii
        self._ref_radii = ref_radii
        self._kernel_type = kernel_type

    def execute(self, II_data: _NDf64, II_ones: _NDf64) -> ArmStats:
        """Compute per-arm sums, counts and ranks from a 2D integral image.

        :param II_data: 2D integral image of the data, shape ``(N0 + 1, N1 + 1)``.
        :param II_ones: 2D integral image of ones (same shape), used to count cells per arm.
        :returns: :class:`ArmStats` whose ``axes[0]`` holds ``[left, right]`` and
            ``axes[1]`` holds ``[near, far]``.
        """
        N0, N1 = II_data.shape[0] - 1, II_data.shape[1] - 1
        g0, g1 = self._guard_radii
        r0, r1 = self._ref_radii

        idx_0 = np.arange(N0)[:, None]
        idx_1 = np.arange(N1)[None, :]

        def clip0(v: _NDint) -> _NDint:
            return np.asarray(np.clip(v, 0, N0), dtype=np.intp)

        def clip1(v: _NDint) -> _NDint:
            return np.asarray(np.clip(v, 0, N1), dtype=np.intp)

        l_start_0 = clip0(idx_0 - g0 - r0)
        l_end_0 = clip0(idx_0 - g0)
        r_start_0 = clip0(idx_0 + g0 + 1)
        r_end_0 = clip0(idx_0 + g0 + r0 + 1)
        n_start_1 = clip1(idx_1 - g1 - r1)
        n_end_1 = clip1(idx_1 - g1)
        f_start_1 = clip1(idx_1 + g1 + 1)
        f_end_1 = clip1(idx_1 + g1 + r1 + 1)

        def box(P: _NDf64, r0_: _NDint, r1_: _NDint, c0: _NDint, c1: _NDint) -> _NDf64:
            return np.asarray(P[r1_, c1] - P[r0_, c1] - P[r1_, c0] + P[r0_, c0], dtype=np.float64)

        if self._kernel_type == CFARKernelType.THIN_CROSS:
            expected_0 = r0
            expected_1 = r1
            now_0, next_0 = idx_0, idx_0 + 1
            now_1, next_1 = idx_1, idx_1 + 1

            axis0_sums = [
                box(II_data, l_start_0, l_end_0, now_1, next_1),
                box(II_data, r_start_0, r_end_0, now_1, next_1),
            ]
            axis0_counts = [
                box(II_ones, l_start_0, l_end_0, now_1, next_1),
                box(II_ones, r_start_0, r_end_0, now_1, next_1),
            ]
            axis1_sums = [
                box(II_data, now_0, next_0, n_start_1, n_end_1),
                box(II_data, now_0, next_0, f_start_1, f_end_1),
            ]
            axis1_counts = [
                box(II_ones, now_0, next_0, n_start_1, n_end_1),
                box(II_ones, now_0, next_0, f_start_1, f_end_1),
            ]
        else:  # THICK_CROSS
            w_start_1 = clip1(idx_1 - g1)
            w_end_1 = clip1(idx_1 + g1 + 1)
            w_start_0 = clip0(idx_0 - g0)
            w_end_0 = clip0(idx_0 + g0 + 1)
            w0 = 2 * g0 + 1
            w1 = 2 * g1 + 1
            expected_0 = r0 * w1
            expected_1 = r1 * w0

            axis0_sums = [
                box(II_data, l_start_0, l_end_0, w_start_1, w_end_1),
                box(II_data, r_start_0, r_end_0, w_start_1, w_end_1),
            ]
            axis0_counts = [
                box(II_ones, l_start_0, l_end_0, w_start_1, w_end_1),
                box(II_ones, r_start_0, r_end_0, w_start_1, w_end_1),
            ]
            axis1_sums = [
                box(II_data, w_start_0, w_end_0, n_start_1, n_end_1),
                box(II_data, w_start_0, w_end_0, f_start_1, f_end_1),
            ]
            axis1_counts = [
                box(II_ones, w_start_0, w_end_0, n_start_1, n_end_1),
                box(II_ones, w_start_0, w_end_0, f_start_1, f_end_1),
            ]

        return ArmStats(
            axes=[
                AxisArmStats(
                    sums=axis0_sums,
                    counts=axis0_counts,
                    ranks=_ranks_for_axis(axis0_counts, expected_count=expected_0),
                ),
                AxisArmStats(
                    sums=axis1_sums,
                    counts=axis1_counts,
                    ranks=_ranks_for_axis(axis1_counts, expected_count=expected_1),
                ),
            ]
        )


# --- Aggregate ---


class CFARAggregateMethod(str, Enum):
    """How to combine reference arms into a single noise estimate."""

    CA = "CA"
    """Cell-averaging: pool all arms into one estimate (CA-CFAR)."""
    GO = "GO"
    """Greatest-of: keep the single arm with the highest mean (GO-CFAR)."""
    SO = "SO"
    """Smallest-of: keep the single arm with the lowest mean (SO-CFAR)."""
    DROP = "DROP"
    """No-op: the aggregator returns all-zero ``(sum, count)`` per cell so the
    axis contributes nothing when pooled. Used by 2D pipelines that want to
    skip one axis without conditional logic in the wrapper."""


class CFARAggregateNode:
    """Combine the arms along one axis into a single ``(sum, count)`` pair.

    The aggregator picks one axis of an :class:`ArmStats` and produces a flat
    ``(sum, count)`` per cell from the arms along that axis. Pooling across
    multiple aggregators (e.g. one per axis in 2D) is done by the caller via
    :class:`AxisPoolNode`.
    """

    def __init__(self, method: CFARAggregateMethod, axis: int = 0):
        """
        :param method: ``CA`` pools the arms on the chosen axis; ``GO`` picks the single arm
            with the highest mean; ``SO`` picks the single arm with the lowest mean; ``DROP``
            is a no-op that returns zero ``(sum, count)`` per cell, so this aggregator
            contributes nothing when pooled. ``GO`` and ``SO`` prefer arms with higher
            ``rank`` (full > partial > empty) and break ties by mean.
        :param axis: Which axis of the input :class:`ArmStats` to operate on. For 1D
            extractors only ``axis=0`` is valid; for 2D use ``axis=0`` for the left/right
            arms or ``axis=1`` for the near/far arms, instantiating one ``CFARAggregateNode``
            per axis.
        """
        self._method = method
        self._axis = axis

    def execute(self, arms: ArmStats) -> t.Tuple[_NDf64, _NDf64]:
        """Aggregate the arms on the configured axis.

        :param arms: Per-axis arm sums, counts and ranks.
        :returns: ``(sum, count)`` arrays of the same shape as the input arms; for ``CA``
            these are the pooled values across the axis, for ``GO``/``SO`` they are the
            chosen arm's values per cell, and for ``DROP`` they are zeros.
        """
        axis_arms = arms.axes[self._axis]

        if self._method == CFARAggregateMethod.DROP:
            zeros = np.zeros_like(axis_arms.sums[0], dtype=np.float64)
            return zeros, zeros.copy()

        if self._method == CFARAggregateMethod.CA:
            s = np.zeros_like(axis_arms.sums[0])
            c = np.zeros_like(axis_arms.counts[0])
            for arm_sum, arm_count in zip(axis_arms.sums, axis_arms.counts):
                s += arm_sum
                c += arm_count
            return np.asarray(s, dtype=np.float64), np.asarray(c, dtype=np.float64)

        return self._select_best(axis_arms, maximize=(self._method == CFARAggregateMethod.GO))

    @staticmethod
    def _select_best(axis_arms: AxisArmStats, maximize: bool) -> t.Tuple[_NDf64, _NDf64]:
        """Pick the arm with highest/lowest mean per cell, preferring higher rank."""
        means = _axis_arm_means(axis_arms)

        best_s = np.asarray(axis_arms.sums[0], dtype=np.float64).copy()
        best_c = np.asarray(axis_arms.counts[0], dtype=np.float64).copy()
        best_r = np.asarray(axis_arms.ranks[0], dtype=np.int8).copy()
        best_m = np.asarray(means[0], dtype=np.float64).copy()

        for i in range(1, len(axis_arms.sums)):
            s_k = axis_arms.sums[i]
            c_k = axis_arms.counts[i]
            r_k = axis_arms.ranks[i]
            m_k = means[i]

            mean_pick = (m_k > best_m) if maximize else (m_k < best_m)
            pick_k = (r_k > best_r) | ((r_k == best_r) & mean_pick)

            best_s = np.where(pick_k, s_k, best_s)
            best_c = np.where(pick_k, c_k, best_c)
            best_r = np.where(pick_k, r_k, best_r)
            best_m = np.where(pick_k, m_k, best_m)

        return np.asarray(best_s, dtype=np.float64), np.asarray(best_c, dtype=np.float64)


# --- Axis pooling ---


class AxisPoolNode:
    """Pool two per-axis ``(sum, count)`` pairs into a single ``(sum, count)``.

    Sums the per-axis sums and counts element-wise — the cross-axis
    aggregation step in 2D CFAR after running one :class:`CFARAggregateNode`
    per axis. The pooled count equals the total number of reference cells
    contributing across both axes, which is what :class:`CFARScalingNode`
    expects for the scaling formula. An axis that should not contribute
    feeds its :class:`CFARAggregateNode` with :attr:`CFARAggregateMethod.DROP`,
    which returns zeros and so leaves the pool unchanged.
    """

    @staticmethod
    def execute(
        axis_0_aggregate: t.Tuple[_NDf64, _NDf64],
        axis_1_aggregate: t.Tuple[_NDf64, _NDf64],
    ) -> t.Tuple[_NDf64, _NDf64]:
        """Pool axis-0 and axis-1 ``(sum, count)`` pairs element-wise.

        :param axis_0_aggregate: ``(sum, count)`` from the axis-0 :class:`CFARAggregateNode`.
        :param axis_1_aggregate: ``(sum, count)`` from the axis-1 :class:`CFARAggregateNode`.
        :returns: ``(pooled_sum, pooled_count)`` with the same shape as the inputs.
        """
        s0, c0 = axis_0_aggregate
        s1, c1 = axis_1_aggregate
        return (
            np.asarray(s0 + s1, dtype=np.float64),
            np.asarray(c0 + c1, dtype=np.float64),
        )


# --- CFAR scaling ---


class CFARScalingNode:
    """Convert ``(arm_sum, N)`` to a CFAR threshold map.

    Computes the noise estimate ``noise_est = arm_sum / N`` and applies
    ``threshold = noise_est · N · (fpr^(−1/N) − 1)`` cell-wise, then clips from
    below by ``fixed_threshold``. Cells with ``N == 0`` (no valid reference
    cells available) get ``threshold = inf``.

    Taking ``arm_sum`` rather than ``noise_est`` lets callers pool sums and
    counts across multiple aggregators (one per axis in 2D) before computing
    the final estimate in a single place.

    The formula is the CA-CFAR scaling derived from i.i.d. exponentially
    distributed reference cells — the noise model for square-law-detected
    radar returns in white Gaussian noise.
    """

    def __init__(self, theoretical_fpr: float, fixed_threshold: float = 0.0):
        """
        :param theoretical_fpr: Target false-positive rate under ideal conditions: independent,
            exponentially distributed reference cells containing only noise. In practice two
            effects disturb this: (1) target energy leaking into reference cells inflates the
            noise estimate and raises the threshold, reducing detection probability for nearby
            targets (masking); (2) correlated samples (adjacent range bins share pulse-shape
            energy) reduce the effective number of independent cells, making the threshold lower
            than the formula predicts. Because of these effects the parameter rarely matches the
            actual FPR and typically needs to be set larger or smaller than the desired operating
            point through ad-hoc tuning.
        :param fixed_threshold: Hard minimum threshold; the computed threshold is clipped to
            at least this value.
        """
        if not (0.0 < theoretical_fpr < 1.0):
            msg = f"theoretical_fpr must be in (0, 1), got {theoretical_fpr}."
            raise ValueError(msg)
        if fixed_threshold < 0.0:
            msg = f"fixed_threshold must be non-negative, got {fixed_threshold}."
            raise ValueError(msg)
        self._fpr = theoretical_fpr
        self._fixed_threshold = fixed_threshold

    def execute(self, arm_sum: _NDf64, num_samples: _NDf64) -> _NDf64:
        """Divide ``arm_sum`` by ``num_samples`` and apply the CFAR scaling formula.

        :param arm_sum: Cell-wise sum of reference-arm values (from one aggregator, or pooled
            across multiple aggregators by adding their ``arm_sum`` outputs).
        :param num_samples: Cell-wise reference-cell count ``N`` matching ``arm_sum`` (also
            poolable across aggregators).
        :returns: Cell-wise threshold map; cells with ``N == 0`` are ``inf``.
        """
        safe_n = np.where(num_samples > 0, num_samples, 1.0)
        noise_est = np.asarray(arm_sum / safe_n, dtype=np.float64)
        scaling = safe_n * (np.power(self._fpr, -1.0 / safe_n) - 1.0)
        scaling = np.where(num_samples > 0, scaling, 0.0)
        threshold = np.asarray(noise_est * scaling, dtype=np.float64)
        threshold[num_samples == 0] = np.inf
        return np.clip(threshold, a_min=self._fixed_threshold, a_max=None)


# --- Sidelobe compensation ---


class SidelobeCompensationNode:
    """Raise the threshold to at least ``max_along_axis(data) · 10^(dB/10)``.

    Protects against detecting strong-target sidelobes as separate targets:
    the threshold can never sit more than ``|dB|`` dB below the per-axis
    maximum. Works on inputs of any dimensionality — for 2D processing along
    both axes, instantiate two nodes (one per axis) and run them in sequence.
    """

    def __init__(self, side_lobe_compensation_dB: t.Optional[float], axis: int = 0):
        """
        :param side_lobe_compensation_dB: dB below the per-axis maximum that the threshold may
            not fall below. Must be smaller than zero when set; ``None`` makes the node a no-op
            (``execute`` returns the input threshold unchanged).
        :param axis: Axis along which to take the maximum. For 1D inputs, ``axis=0`` collapses
            across the only axis. For 2D inputs, ``axis=0`` derives a per-column floor and
            ``axis=1`` a per-row floor.
        """
        if side_lobe_compensation_dB is not None and side_lobe_compensation_dB >= 0.0:
            msg = (
                f"side_lobe_compensation_dB must be smaller than zero or None "
                f"got {side_lobe_compensation_dB}."
            )
            raise ValueError(msg)
        self._dB = side_lobe_compensation_dB
        self._axis = axis

    def execute(self, threshold: _NDf64, data: _NDf64) -> _NDf64:
        """Raise the threshold to at least ``max_along_axis(data) · 10^(dB/10)``.

        :param threshold: Cell-wise threshold from upstream stages.
        :param data: Original input array used to derive the per-axis maximum.
        :returns: Threshold with the sidelobe floor applied element-wise, or the input
            threshold unchanged if ``side_lobe_compensation_dB`` is ``None``.
        """
        if self._dB is None:
            return np.asarray(threshold, dtype=np.float64)
        floor = np.max(data, axis=self._axis, keepdims=True) * (10.0 ** (self._dB / 10.0))
        return np.asarray(np.maximum(threshold, floor), dtype=np.float64)
