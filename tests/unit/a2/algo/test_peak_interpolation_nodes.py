# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for the peak-interpolation nodes in ``_peak_interpolation_nodes``:

* ``Interpolation1DNode`` — sub-sample refinement of 1D peak indices.
* ``Peak1DInterpolationNode`` — stacked sub-sample refinement; one peak per
  row of an ``(N, K)`` data stack.
* ``Interpolation2DNode`` — sub-sample refinement of 2D peak indices.

The fitted methods (GAUSSIAN, GAUSSIAN_INDEPENDENT, GAUSSIAN_2D) are
exercised with analytic Gaussian samples whose true sub-sample offsets are
known by construction; the log-domain fit is exact for noiseless input, so
tight tolerances (``abs=1e-9``) hold.

The module-level private helpers ``_gaussian_offset_1d``,
``_gaussian_offset_lstsq`` and ``_idx_to_val`` are tested directly because
they pin numerical edge cases (degenerate denominator, concave-up parabola,
axis clipping) without requiring the full node setup.
"""

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import (
    Interpolation1DNode,
    Interpolation2DNode,
    InterpolationMethod1D,
    InterpolationMethod2D,
    Peak1DInterpolationNode,
    _gaussian_offset_1d,
    _gaussian_offset_lstsq,
    _idx_to_val,
)


_NDf64 = npt.NDArray[np.float64]


def _gaussian_1d(coords: _NDf64, mu: float, sigma: float = 1.0) -> _NDf64:
    """Sample a 1D Gaussian at ``coords``."""
    return t.cast(_NDf64, np.exp(-0.5 * ((coords - mu) / sigma) ** 2).astype(np.float64))


def _gaussian_2d_grid(
    rows: int,
    cols: int,
    mu_r: float,
    mu_c: float,
    sigma: float = 1.0,
) -> _NDf64:
    """Sample a separable isotropic 2D Gaussian on a ``[0..rows) x [0..cols)`` grid."""
    rr, cc = np.meshgrid(np.arange(rows, dtype=float), np.arange(cols, dtype=float), indexing="ij")
    return t.cast(
        _NDf64,
        np.exp(-0.5 * (((rr - mu_r) ** 2 + (cc - mu_c) ** 2) / sigma**2)).astype(np.float64),
    )


# --- module helpers ---


class TestModuleHelpers:
    # _gaussian_offset_1d ----------------------------------------------------

    def test_g1d_symmetric_returns_zero(self) -> None:
        y = _gaussian_1d(np.arange(3, dtype=float), mu=1.0)
        assert _gaussian_offset_1d(y) == pytest.approx(0.0, abs=1e-12)

    def test_g1d_recovers_known_offset(self) -> None:
        # Gaussian centered at 1.3 sampled at i=0,1,2; peak index 1, offset 0.3.
        y = _gaussian_1d(np.arange(3, dtype=float), mu=1.3)
        assert _gaussian_offset_1d(y) == pytest.approx(0.3, abs=1e-9)

    def test_g1d_short_input_returns_zero(self) -> None:
        assert _gaussian_offset_1d(np.array([1.0, 2.0])) == 0.0

    def test_g1d_non_positive_returns_zero(self) -> None:
        # Any non-positive value disqualifies the log domain.
        assert _gaussian_offset_1d(np.array([1.0, 2.0, 0.0])) == 0.0
        assert _gaussian_offset_1d(np.array([1.0, 2.0, -0.5])) == 0.0

    def test_g1d_flat_returns_zero(self) -> None:
        # ly[0] - 2*ly[1] + ly[2] == 0 -> den ~ 0 -> return 0.
        assert _gaussian_offset_1d(np.array([1.0, 1.0, 1.0])) == 0.0

    def test_g1d_clips_to_half(self) -> None:
        # Monotonically decreasing [10, 5, 1] is concave-down (den < 0) but its
        # parabolic vertex sits past x = -0.5 -> clipped to -0.5. A real peak
        # detector wouldn't hand this window in (y[1] isn't the local max), but
        # the clip is the defensive backstop for that case.
        assert _gaussian_offset_1d(np.array([10.0, 5.0, 1.0])) == pytest.approx(-0.5, abs=1e-9)

    def test_g1d_concave_up_returns_zero(self) -> None:
        # [1, 2, 5] is concave-up in log-domain: no maximum in the window.
        # The 3-pt variant silently returns 0 rather than reporting the
        # parabola's minimum location clipped to -0.5.
        assert _gaussian_offset_1d(np.array([1.0, 2.0, 5.0])) == 0.0

    # _gaussian_offset_lstsq -------------------------------------------------

    def test_lstsq_symmetric_returns_zero(self) -> None:
        # 5-point centered Gaussian.
        y = _gaussian_1d(np.arange(5, dtype=float), mu=2.0)
        assert _gaussian_offset_lstsq(y, start_rel=-2) == pytest.approx(0.0, abs=1e-9)

    def test_lstsq_recovers_known_offset(self) -> None:
        # 5-point Gaussian at i=0..4 centered at 2.3. Peak index 2 -> offset 0.3.
        y = _gaussian_1d(np.arange(5, dtype=float), mu=2.3)
        assert _gaussian_offset_lstsq(y, start_rel=-2) == pytest.approx(0.3, abs=1e-9)

    def test_lstsq_excludes_non_positive(self) -> None:
        # Zeroing the first sample leaves four valid points; the fit still recovers 0.3.
        y = _gaussian_1d(np.arange(5, dtype=float), mu=2.3)
        y[0] = 0.0
        assert _gaussian_offset_lstsq(y, start_rel=-2) == pytest.approx(0.3, abs=1e-9)

    def test_lstsq_too_few_valid_returns_zero(self) -> None:
        y = np.array([0.0, 0.0, 1.0, 0.0, 0.0])
        assert _gaussian_offset_lstsq(y, start_rel=-2) == 0.0

    def test_lstsq_concave_up_returns_zero(self) -> None:
        # y rises away from center -> c2 >= 0 -> early return of 0.0 (silent).
        x = np.arange(5, dtype=float) - 2
        y = np.exp(0.1 * x**2)
        assert _gaussian_offset_lstsq(y, start_rel=-2) == 0.0

    def test_lstsq_clips_to_half(self) -> None:
        # Construct exp(c1*x + c2*x²) with peak at -c1/(2*c2) = 2.0 -> clipped to 0.5.
        x = np.arange(5, dtype=float) - 2
        y = np.exp(4.0 * x - 1.0 * x**2)
        assert _gaussian_offset_lstsq(y, start_rel=-2) == 0.5

    # _idx_to_val ------------------------------------------------------------

    def test_idx_to_val_integer(self) -> None:
        axis = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        assert _idx_to_val(axis, 2) == 2.0

    def test_idx_to_val_fractional_uniform(self) -> None:
        axis = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        assert _idx_to_val(axis, 2.5) == 2.5

    def test_idx_to_val_negative_returns_first(self) -> None:
        # Covers idx in (-1, 0) too: e.g. index=0 with a clipped Gaussian offset of -0.5
        # produces idx=-0.5, which must clip to axis[0] rather than extrapolate below it.
        axis = np.array([10.0, 20.0, 30.0])
        assert _idx_to_val(axis, -0.5) == 10.0
        assert _idx_to_val(axis, -1.0) == 10.0
        assert _idx_to_val(axis, -5.0) == 10.0

    def test_idx_to_val_past_last_returns_last(self) -> None:
        axis = np.array([10.0, 20.0, 30.0])
        assert _idx_to_val(axis, 2.0) == 30.0
        assert _idx_to_val(axis, 2.5) == 30.0
        assert _idx_to_val(axis, 5.0) == 30.0

    def test_idx_to_val_non_uniform(self) -> None:
        axis = np.array([0.0, 1.0, 4.0, 10.0])
        # idx=1.5 -> between axis[1]=1 and axis[2]=4: 1 + 0.5*(4-1) = 2.5.
        assert _idx_to_val(axis, 1.5) == 2.5
        # idx=2.25 -> between axis[2]=4 and axis[3]=10: 4 + 0.25*(10-4) = 5.5.
        assert _idx_to_val(axis, 2.25) == 5.5


# --- Interpolation1DNode ---


class TestInterpolation1DNode:
    def test_default_method_and_radius(self) -> None:
        # Defaults: GAUSSIAN, radius=1. Symmetric 3-pt Gaussian -> offset 0.
        data = _gaussian_1d(np.arange(3, dtype=float), mu=1.0)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis).execute(data, [1])
        assert len(peaks) == 1
        assert peaks[0].index == 1
        assert peaks[0].amplitude == pytest.approx(float(data[1]))
        assert peaks[0].position == pytest.approx(1.0, abs=1e-9)

    def test_empty_indices(self) -> None:
        data = np.array([1.0, 2.0, 1.0])
        axis = np.arange(3, dtype=float)
        assert Interpolation1DNode(axis).execute(data, []) == []

    def test_multiple_indices_preserve_order(self) -> None:
        data = np.array([0.0, 3.0, 1.0, 5.0, 0.0])
        axis = np.arange(5, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.NONE).execute(data, [3, 1])
        assert [p.index for p in peaks] == [3, 1]
        assert [p.amplitude for p in peaks] == [5.0, 3.0]


class TestInterpolation1DNone:
    def test_position_is_axis_at_index(self) -> None:
        data = np.array([0.0, 2.0, 1.0])
        axis = np.array([10.0, 25.0, 100.0])
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.NONE).execute(data, [1, 2])
        assert peaks[0].position == 25.0
        assert peaks[1].position == 100.0


class TestInterpolation1DGaussian:
    def test_symmetric_no_shift(self) -> None:
        data = _gaussian_1d(np.arange(3, dtype=float), mu=1.0)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [1])
        assert peaks[0].position == pytest.approx(1.0, abs=1e-9)

    def test_recovers_known_offset(self) -> None:
        data = _gaussian_1d(np.arange(3, dtype=float), mu=1.3)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [1])
        assert peaks[0].position == pytest.approx(1.3, abs=1e-9)

    def test_non_positive_in_window_returns_index(self) -> None:
        data = np.array([0.0, 1.0, 0.5])
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [1])
        assert peaks[0].position == 1.0

    def test_boundary_window_too_short_returns_index(self) -> None:
        # index=0, radius=1 -> window data[0:2] of length 2; 3-pt formula returns 0.
        data = np.array([5.0, 1.0, 0.5])
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [0])
        assert peaks[0].position == 0.0

    def test_radius_two_uses_lstsq(self) -> None:
        # 5-point Gaussian centered at μ=2.3 -> lstsq recovers offset 0.3.
        data = _gaussian_1d(np.arange(5, dtype=float), mu=2.3)
        axis = np.arange(5, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN, radius=2).execute(
            data, [2]
        )
        assert peaks[0].position == pytest.approx(2.3, abs=1e-9)


class TestInterpolation1DValidation:
    def test_rejects_2d_data(self) -> None:
        with pytest.raises(ValueError, match="1D array"):
            Interpolation1DNode(np.zeros(2)).execute(np.zeros((2, 2)), [0])

    def test_rejects_data_length_mismatch(self) -> None:
        with pytest.raises(ValueError, match="1D array of length"):
            Interpolation1DNode(np.zeros(4)).execute(np.zeros(3), [1])

    def test_rejects_2d_axis(self) -> None:
        with pytest.raises(ValueError, match="axis_grid must be a 1D array"):
            Interpolation1DNode(np.zeros((1, 3)))

    def test_rejects_index_out_of_range(self) -> None:
        data = np.array([1.0, 2.0, 1.0])
        axis = np.arange(3, dtype=float)
        # numpy's IndexError from ``data[i]`` fires before the explicit bounds check.
        with pytest.raises(IndexError, match="out of bounds"):
            Interpolation1DNode(axis).execute(data, [3])


class TestInterpolation1DEdgeCases:
    def test_axis_non_uniform_blend(self) -> None:
        # Refined index 1.3 -> position = axis[1] + 0.3*(axis[2]-axis[1]) = 1 + 0.3*3 = 1.9.
        data = _gaussian_1d(np.arange(3, dtype=float), mu=1.3)
        axis = np.array([0.0, 1.0, 4.0])
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [1])
        assert peaks[0].position == pytest.approx(1.9, abs=1e-9)

    def test_gaussian_clips_to_half(self) -> None:
        # Monotonically decreasing [10, 5, 1] -> concave-down parabola whose vertex
        # sits past x = -0.5 -> clipped to -0.5. Refined index = 1 + (-0.5) = 0.5 ->
        # position 0.5 on a uniform [0, 1, 2] axis. (The fixed _idx_to_val no longer
        # extrapolates below axis[0] for idx in (-1, 0), but 0.5 is inside the axis.)
        data = np.array([10.0, 5.0, 1.0])
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [1])
        assert peaks[0].position == pytest.approx(0.5, abs=1e-9)

    def test_gaussian_concave_up_position_stays_at_index(self) -> None:
        # Concave-up window: the node silently leaves the position at the
        # integer index (no refinement applied).
        data = np.array([1.0, 2.0, 5.0])
        axis = np.arange(3, dtype=float)
        peaks = Interpolation1DNode(axis, method=InterpolationMethod1D.GAUSSIAN).execute(data, [1])
        assert peaks[0].position == pytest.approx(1.0, abs=1e-12)


# --- Peak1DInterpolationNode ---


class TestPeak1DInterpolationNode:
    def test_empty_input(self) -> None:
        axis = np.arange(5, dtype=float)
        out = Peak1DInterpolationNode(axis).execute(np.empty((0, 5)), np.array([], dtype=np.intp))
        assert out == []

    def test_single_row_matches_interpolation_1d(self) -> None:
        axis = np.arange(5, dtype=float)
        data = _gaussian_1d(axis, mu=2.3)
        stack = data.reshape(1, 5)
        out = Peak1DInterpolationNode(axis).execute(stack, np.array([2], dtype=np.intp))
        assert len(out) == 1
        assert out[0].index == 2
        assert out[0].amplitude == pytest.approx(float(data[2]))
        assert out[0].position == pytest.approx(2.3, abs=1e-9)

    def test_multiple_rows_each_with_own_index_and_data(self) -> None:
        axis = np.arange(5, dtype=float)
        row0 = _gaussian_1d(axis, mu=1.2)
        row1 = _gaussian_1d(axis, mu=3.4)
        stack = np.stack([row0, row1])
        out = Peak1DInterpolationNode(axis).execute(stack, np.array([1, 3], dtype=np.intp))
        assert [p.index for p in out] == [1, 3]
        assert out[0].position == pytest.approx(1.2, abs=1e-9)
        assert out[1].position == pytest.approx(3.4, abs=1e-9)

    def test_rejects_1d_stack(self) -> None:
        axis = np.arange(5, dtype=float)
        with pytest.raises(ValueError, match="2D array"):
            Peak1DInterpolationNode(axis).execute(np.zeros(5), np.array([0], dtype=np.intp))

    def test_rejects_axis_length_mismatch(self) -> None:
        axis = np.arange(5, dtype=float)
        with pytest.raises(ValueError, match="match axis length"):
            Peak1DInterpolationNode(axis).execute(np.zeros((1, 4)), np.array([0], dtype=np.intp))

    def test_rejects_indices_length_mismatch(self) -> None:
        axis = np.arange(5, dtype=float)
        with pytest.raises(ValueError, match="does not match stack rows"):
            Peak1DInterpolationNode(axis).execute(np.zeros((2, 5)), np.array([0], dtype=np.intp))

    def test_boundary_lower_argmax_does_not_raise(self) -> None:
        # argmax at index 0: the window straddles the left boundary; Interpolation1DNode
        # clips it and falls back to the grid value at the boundary index.
        axis = np.array([-10.0, -5.0, 0.0, 5.0, 10.0])
        data = np.array([[5.0, 1.0, 0.5, 0.25, 0.0]])
        out = Peak1DInterpolationNode(axis).execute(data, np.array([0], dtype=np.intp))
        assert out[0].index == 0
        assert out[0].position == axis[0]

    def test_boundary_upper_argmax_does_not_raise(self) -> None:
        # argmax at index K-1: same clip behaviour at the right boundary.
        axis = np.array([-10.0, -5.0, 0.0, 5.0, 10.0])
        data = np.array([[0.0, 0.25, 0.5, 1.0, 5.0]])
        out = Peak1DInterpolationNode(axis).execute(data, np.array([4], dtype=np.intp))
        assert out[0].index == 4
        assert out[0].position == axis[-1]


# --- Interpolation2DNode ---


class TestInterpolation2DNode:
    def test_default_method_and_radius(self) -> None:
        # Default: GAUSSIAN_INDEPENDENT, radius=(1,1). Symmetric 3x3 Gaussian -> no shift.
        data = _gaussian_2d_grid(3, 3, mu_r=1.0, mu_c=1.0)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(axis, axis).execute(data, [(1, 1)])
        assert len(peaks) == 1
        assert peaks[0].index == (1, 1)
        assert peaks[0].amplitude == pytest.approx(float(data[1, 1]))
        assert peaks[0].position == pytest.approx((1.0, 1.0), abs=1e-9)

    def test_empty_indices(self) -> None:
        data = np.ones((3, 3))
        axis = np.arange(3, dtype=float)
        assert Interpolation2DNode(axis, axis).execute(data, []) == []

    def test_multiple_indices_preserve_order(self) -> None:
        data = np.zeros((3, 3))
        data[0, 0] = 7.0
        data[2, 2] = 5.0
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(axis, axis, method=InterpolationMethod2D.NONE).execute(
            data, [(2, 2), (0, 0)]
        )
        assert [p.index for p in peaks] == [(2, 2), (0, 0)]
        assert [p.amplitude for p in peaks] == [5.0, 7.0]


class TestInterpolation2DNone:
    def test_position_is_axis_at_index(self) -> None:
        data = np.zeros((3, 3))
        data[1, 2] = 5.0
        axis0 = np.array([10.0, 20.0, 30.0])
        axis1 = np.array([0.0, 5.0, 9.0])
        peaks = Interpolation2DNode(axis0, axis1, method=InterpolationMethod2D.NONE).execute(
            data, [(1, 2)]
        )
        assert peaks[0].position == (20.0, 9.0)


class TestInterpolation2DGaussianIndependent:
    def test_symmetric_3x3_no_shift(self) -> None:
        data = _gaussian_2d_grid(3, 3, mu_r=1.0, mu_c=1.0)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(
            axis, axis, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT
        ).execute(data, [(1, 1)])
        assert peaks[0].position == pytest.approx((1.0, 1.0), abs=1e-9)

    def test_recovers_per_axis_offsets_3x3(self) -> None:
        # Separable shifted Gaussian: center row/col are 3-pt Gaussian slices that the
        # fast 3-pt formula resolves exactly.
        data = _gaussian_2d_grid(3, 3, mu_r=1.2, mu_c=0.8)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(
            axis, axis, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT
        ).execute(data, [(1, 1)])
        assert peaks[0].position == pytest.approx((1.2, 0.8), abs=1e-9)

    def test_recovers_per_axis_offsets_5x5_lstsq(self) -> None:
        # 5x5 patch -> both axes hit the lstsq branch (cols != 3, rows != 3).
        data = _gaussian_2d_grid(5, 5, mu_r=2.3, mu_c=1.7)
        axis = np.arange(5, dtype=float)
        peaks = Interpolation2DNode(
            axis, axis, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT, radius=(2, 2)
        ).execute(data, [(2, 2)])
        assert peaks[0].position == pytest.approx((2.3, 1.7), abs=1e-9)

    def test_boundary_clipped_patch_does_not_misuse_3pt_shortcut_col(self) -> None:
        # Regression: at a boundary, a clipped 3-cell patch must NOT use the
        # 3-point shortcut, which assumes the peak sits at y[1]. With
        # radius=(0, 2) and peak at (0, 0), c_start=0, c_end=3, cols=3, but
        # col_start_rel=0 (peak at y[0], not y[1]). The shortcut would treat
        # y[1] as the peak and produce a non-zero clipped offset; the lstsq
        # branch with start_rel=0 finds a concave-up parabola here and
        # silently returns 0, so position[1] must equal the boundary grid
        # value axis1[0].
        data = np.array([[5.0, 3.0, 4.0]])
        axis0 = np.array([0.0])
        axis1 = np.array([0.0, 1.0, 2.0])
        peaks = Interpolation2DNode(
            axis0, axis1, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT, radius=(0, 2)
        ).execute(data, [(0, 0)])
        assert peaks[0].position == pytest.approx((0.0, 0.0), abs=1e-9)

    def test_boundary_clipped_patch_does_not_misuse_3pt_shortcut_row(self) -> None:
        # Mirror of the col-boundary case along axis 0.
        data = np.array([[5.0], [3.0], [4.0]])
        axis0 = np.array([0.0, 1.0, 2.0])
        axis1 = np.array([0.0])
        peaks = Interpolation2DNode(
            axis0, axis1, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT, radius=(2, 0)
        ).execute(data, [(0, 0)])
        assert peaks[0].position == pytest.approx((0.0, 0.0), abs=1e-9)


class TestInterpolation2DGaussian2D:
    def test_centered_isotropic_no_shift(self) -> None:
        data = _gaussian_2d_grid(3, 3, mu_r=1.0, mu_c=1.0)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(axis, axis, method=InterpolationMethod2D.GAUSSIAN_2D).execute(
            data, [(1, 1)]
        )
        assert peaks[0].position == pytest.approx((1.0, 1.0), abs=1e-9)

    def test_separable_shifted_recovers_offset(self) -> None:
        # Separable (no cross term) so the closed-form solution simplifies to
        # row_offset = mu_r - 1, col_offset = mu_c - 1.
        data = _gaussian_2d_grid(3, 3, mu_r=1.3, mu_c=0.7)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(axis, axis, method=InterpolationMethod2D.GAUSSIAN_2D).execute(
            data, [(1, 1)]
        )
        assert peaks[0].position == pytest.approx((1.3, 0.7), abs=1e-9)

    def test_too_few_valid_pixels_falls_back(self) -> None:
        # Only the center pixel is positive -> <6 valid -> falls back to
        # GAUSSIAN_INDEPENDENT, which also yields (0, 0) on this degenerate patch.
        data = np.zeros((3, 3))
        data[1, 1] = 5.0
        axis = np.arange(3, dtype=float)
        peaks_2d = Interpolation2DNode(
            axis, axis, method=InterpolationMethod2D.GAUSSIAN_2D
        ).execute(data, [(1, 1)])
        peaks_indep = Interpolation2DNode(
            axis, axis, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT
        ).execute(data, [(1, 1)])
        assert peaks_2d[0].position == peaks_indep[0].position
        assert peaks_2d[0].position == (1.0, 1.0)

    def test_singular_det_falls_back(self) -> None:
        # Uniform positive patch -> fit returns ~0 for all quadratic coefficients
        # -> det ~ 0 -> falls back. GAUSSIAN_INDEPENDENT also returns 0 here.
        data = np.ones((3, 3))
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(axis, axis, method=InterpolationMethod2D.GAUSSIAN_2D).execute(
            data, [(1, 1)]
        )
        assert peaks[0].position == pytest.approx((1.0, 1.0), abs=1e-9)

    def test_recovers_offset_with_cross_term(self) -> None:
        # The other tests in this class use isotropic Gaussians, which have no
        # cross term in the log-quadratic fit; that exercises the gamma=0 path
        # only. Construct a patch directly from a log-quadratic with non-zero
        # gamma so the full Hessian-inverse closed form is exercised.
        #
        # ln f(r, c) = p*r + q*c + alpha*r^2 + beta*c^2 + gamma*r*c
        # Pick alpha=beta=-2, gamma=1, peak at (r*, c*) = (0.2, 0.2).
        # Peak constraints: p = -2*alpha*r* - gamma*c* = 0.6;
        #                   q = -gamma*r* - 2*beta*c*  = 0.6.
        alpha, beta, gamma = -2.0, -2.0, 1.0
        p, q = 0.6, 0.6
        rr, cc = np.meshgrid(np.arange(-1, 2), np.arange(-1, 2), indexing="ij")
        rr = rr.astype(np.float64)
        cc = cc.astype(np.float64)
        log_f = p * rr + q * cc + alpha * rr * rr + beta * cc * cc + gamma * rr * cc
        data = np.exp(log_f).astype(np.float64)
        axis = np.arange(3, dtype=float)
        peaks = Interpolation2DNode(axis, axis, method=InterpolationMethod2D.GAUSSIAN_2D).execute(
            data, [(1, 1)]
        )
        assert peaks[0].position == pytest.approx((1.2, 1.2), abs=1e-9)


class TestInterpolation2DValidation:
    def test_rejects_1d_data(self) -> None:
        with pytest.raises(ValueError, match="2D array"):
            Interpolation2DNode(np.zeros(3), np.zeros(3)).execute(np.zeros(3), [(0, 0)])

    def test_rejects_3d_data(self) -> None:
        with pytest.raises(ValueError, match="2D array"):
            Interpolation2DNode(np.zeros(2), np.zeros(2)).execute(np.zeros((2, 2, 2)), [(0, 0)])

    def test_rejects_data_shape_mismatch_axis0(self) -> None:
        with pytest.raises(ValueError, match=r"2D array of shape \(2, 3\)"):
            Interpolation2DNode(np.zeros(2), np.zeros(3)).execute(np.zeros((3, 3)), [(0, 0)])

    def test_rejects_data_shape_mismatch_axis1(self) -> None:
        with pytest.raises(ValueError, match=r"2D array of shape \(3, 2\)"):
            Interpolation2DNode(np.zeros(3), np.zeros(2)).execute(np.zeros((3, 3)), [(0, 0)])

    def test_rejects_2d_axis0(self) -> None:
        with pytest.raises(ValueError, match="axis0_grid must be a 1D array"):
            Interpolation2DNode(np.zeros((1, 3)), np.zeros(3))

    def test_rejects_2d_axis1(self) -> None:
        with pytest.raises(ValueError, match="axis1_grid must be a 1D array"):
            Interpolation2DNode(np.zeros(3), np.zeros((1, 3)))

    def test_rejects_index_out_of_bounds(self) -> None:
        data = np.zeros((3, 3))
        axis = np.arange(3, dtype=float)
        # numpy's IndexError from ``data[r, c]`` fires before the explicit bounds check.
        with pytest.raises(IndexError, match="out of bounds"):
            Interpolation2DNode(axis, axis).execute(data, [(3, 0)])
        with pytest.raises(IndexError, match="out of bounds"):
            Interpolation2DNode(axis, axis).execute(data, [(0, 3)])


class TestInterpolation2DEdgeCases:
    def test_asymmetric_radius(self) -> None:
        # Peak at (1, 2) on a 3x5 grid with radius=(1, 2) -> 3x5 patch.
        # Center row (cols=5) hits the lstsq branch on the col axis;
        # center col (rows=3) hits the 3-pt formula on the row axis.
        data = _gaussian_2d_grid(3, 5, mu_r=1.0, mu_c=2.3)
        axis0 = np.arange(3, dtype=float)
        axis1 = np.arange(5, dtype=float)
        peaks = Interpolation2DNode(
            axis0, axis1, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT, radius=(1, 2)
        ).execute(data, [(1, 2)])
        assert peaks[0].position == pytest.approx((1.0, 2.3), abs=1e-9)

    def test_non_uniform_axes(self) -> None:
        # Refined index (1.3, 1.4):
        #   row -> axis0[1] + 0.3*(axis0[2]-axis0[1]) = 10 + 0.3*20 = 16.
        #   col -> axis1[1] + 0.4*(axis1[2]-axis1[1]) = 2 + 0.4*6 = 4.4.
        data = _gaussian_2d_grid(3, 3, mu_r=1.3, mu_c=1.4)
        axis0 = np.array([0.0, 10.0, 30.0])
        axis1 = np.array([0.0, 2.0, 8.0])
        peaks = Interpolation2DNode(
            axis0, axis1, method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT
        ).execute(data, [(1, 1)])
        assert peaks[0].position == pytest.approx((16.0, 4.4), abs=1e-9)
