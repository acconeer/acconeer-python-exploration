# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum

import attrs
import numpy as np
import numpy.typing as npt


_NDf64 = npt.NDArray[np.float64]

_NEAR_ZERO: float = 1e-9


@attrs.frozen
class Peak1D:
    """Detected and refined peak in a 1D signal."""

    index: int
    """Integer index of the detected peak in the data array."""

    amplitude: float
    """Data value at the peak index."""

    position: float
    """Refined physical position on the axis grid."""


@attrs.frozen
class Peak2D:
    """Detected and refined peak in a 2D signal."""

    index: tuple[int, int]
    """(row, col) integer index of the detected peak."""

    amplitude: float
    """Data value at the peak index."""

    position: tuple[float, float]
    """Refined physical position (axis0_val, axis1_val)."""


class InterpolationMethod1D(str, Enum):
    """Sub-sample peak refinement method for 1D local maxima."""

    NONE = "NONE"
    """No refinement; the integer index is returned as-is."""
    GAUSSIAN = "GAUSSIAN"
    """Gaussian peak fit; uses the fast 3-point formula for radius=1, least squares for radius>1."""


class InterpolationMethod2D(str, Enum):
    """Sub-sample peak refinement method for 2D local maxima."""

    NONE = "NONE"
    """No refinement; the integer index is returned as-is."""
    GAUSSIAN_INDEPENDENT = "GAUSSIAN_INDEPENDENT"
    """Separable: fits 1D Gaussians on each axis independently (fast, robust)."""
    GAUSSIAN_2D = "GAUSSIAN_2D"
    """True 2D Gaussian surface fit via least squares (most accurate)."""


def _gaussian_offset_1d(y: _NDf64) -> float:
    """
    3-point log-domain Gaussian peak interpolation.
    Returns sub-sample offset relative to the center of the provided slice.

    Returns 0.0 for slices shorter than 3, with non-positive values, with a
    near-flat log profile, or with a parabola that is not concave-down (i.e.
    no interior maximum in the fitted window). Result is clipped to
    [-0.5, 0.5].
    """
    n = len(y)
    if n < 3:
        return 0.0

    if np.any(y <= _NEAR_ZERO):
        return 0.0

    ly = np.log(y)
    num = ly[0] - ly[2]
    den = 2 * (ly[0] - 2 * ly[1] + ly[2])

    if abs(den) < _NEAR_ZERO:
        return 0.0

    if den > 0:
        return 0.0

    return float(np.clip(num / den, -0.5, 0.5))


def _gaussian_offset_lstsq(y: _NDf64, start_rel: int) -> float:
    """
    Log-domain least-squares Gaussian fit for windows wider than 3 points.

    Fits ln(y) = c0 + c1*x + c2*x² by least squares where x are pixel coordinates
    relative to the peak (start_rel is the coordinate of y[0]). Entries with y ≤ 0
    are excluded from the fit.

    Returns 0.0 if fewer than 3 valid points remain or the fitted parabola is
    not concave-down (i.e. no interior maximum in the fitted window). Result
    is clipped to [-0.5, 0.5].
    """
    coords = np.arange(len(y), dtype=float) + start_rel
    valid = y > _NEAR_ZERO
    if np.sum(valid) < 3:
        return 0.0
    x = coords[valid]
    z = np.log(y[valid])
    A = np.column_stack([np.ones(len(x)), x, x * x])
    theta, _, _, _ = np.linalg.lstsq(A, z, rcond=None)
    c1, c2 = theta[1], theta[2]
    if c2 >= -_NEAR_ZERO:
        return 0.0
    return float(np.clip(-c1 / (2.0 * c2), -0.5, 0.5))


def _idx_to_val(axis_grid: _NDf64, idx: float) -> float:
    """Linearly maps a fractional index to a physical value on the axis grid."""
    i = int(np.floor(idx))
    rem = idx - i

    if i < 0:
        return float(axis_grid[0])
    if i >= len(axis_grid) - 1:
        return float(axis_grid[-1])

    return float(axis_grid[i] + (axis_grid[i + 1] - axis_grid[i]) * rem)


class Interpolation1DNode:
    """Sub-sample position refinement for a list of 1D peak indices.

    Takes a list of integer indices (e.g. from :class:`LocalMaxima1DNode`) and
    refines each to a physical position on the provided axis grid. Also populates
    amplitude from the data array.
    """

    def __init__(
        self,
        axis_grid: _NDf64,
        method: InterpolationMethod1D = InterpolationMethod1D.GAUSSIAN,
        radius: int = 1,
    ) -> None:
        """
        :param axis_grid: Physical axis grid of shape ``(N,)``. ``execute`` validates
            the input data length against this.
        :param method: Sub-sample refinement method.
        :param radius: Half-width in samples of the interpolation window.
            ``GAUSSIAN`` with ``radius=1`` uses the fast 3-point analytical formula;
            ``radius>1`` switches to least squares.
        """
        if axis_grid.ndim != 1:
            msg = f"axis_grid must be a 1D array, got shape {axis_grid.shape}"
            raise ValueError(msg)
        self._axis_grid = axis_grid
        self._method = method
        self._radius = radius

    def execute(
        self,
        data: _NDf64,
        indices: list[int],
    ) -> list[Peak1D]:
        """Refine a list of integer peak indices to physical positions.

        :param data: 1D data array of shape ``(N,)``, matching the configured axis length.
        :param indices: List of integer peak indices.
        :returns: List of :class:`Peak1D` in the same order as ``indices``.
        """
        if data.ndim != 1:
            msg = f"data must be a 1D array, got shape {data.shape}"
            raise ValueError(msg)
        if len(data) != len(self._axis_grid):
            msg = (
                f"data must be a 1D array of length {len(self._axis_grid)}, got shape {data.shape}"
            )
            raise ValueError(msg)

        peaks = [
            Peak1D(
                index=i,
                amplitude=float(data[i]),
                position=self._interpolate_at(data, i),
            )
            for i in indices
        ]
        return peaks

    def _interpolate_at(
        self,
        data: _NDf64,
        index: int,
    ) -> float:
        """Refine the physical position of a single peak at the given integer index.

        :param data: 1D data array.
        :param index: Integer index of the peak.
        :returns: Refined physical position.
        """
        N = len(data)
        radius = self._radius

        if self._method == InterpolationMethod1D.NONE:
            offset = 0.0
        elif self._method == InterpolationMethod1D.GAUSSIAN:
            start = max(0, index - radius)
            end = min(N, index + radius + 1)
            y = data[start:end]
            start_rel = start - index
            if radius == 1:
                offset = _gaussian_offset_1d(y)
            else:
                offset = _gaussian_offset_lstsq(y, start_rel)
        else:
            offset = 0.0

        return _idx_to_val(self._axis_grid, float(index) + offset)


class Peak1DInterpolationNode:
    """Stacked 1D sub-sample interpolation: one refined peak per input row.

    Wraps :class:`Interpolation1DNode` over a stack of 1D arrays sharing a
    common axis grid. Input is an ``(N, K)`` stack plus length-``N`` integer
    indices (one peak per row); output is a list of ``N`` :class:`Peak1D` in
    row order.

    Use this when the 1D slices come from somewhere other than a fixed
    heatmap layout (e.g. per-peak conventional beamforming over elevation),
    so the interpolation step doesn't have to know how the rows were built.
    """

    def __init__(
        self,
        axis_grid: _NDf64,
        method: InterpolationMethod1D = InterpolationMethod1D.GAUSSIAN,
        radius: int = 1,
    ) -> None:
        """
        :param axis_grid: Physical axis grid of shape ``(K,)`` shared by every row.
        :param method: Sub-sample refinement method.
        :param radius: Half-width in samples of the interpolation window.
        """
        self._inner = Interpolation1DNode(axis_grid=axis_grid, method=method, radius=radius)
        self._axis_len = len(axis_grid)

    def execute(
        self,
        stack: _NDf64,
        indices: npt.NDArray[np.intp],
    ) -> list[Peak1D]:
        """Refine one peak per row of ``stack``.

        :param stack: ``(N, K)`` data array; each row is a 1D slice over the
            configured axis.
        :param indices: ``(N,)`` integer peak index per row.
        :returns: List of ``N`` :class:`Peak1D` in row order.
        """
        if stack.ndim != 2:
            msg = f"stack must be a 2D array, got shape {stack.shape}"
            raise ValueError(msg)
        if stack.shape[1] != self._axis_len:
            msg = f"stack columns must match axis length {self._axis_len}, got shape {stack.shape}"
            raise ValueError(msg)
        if len(indices) != stack.shape[0]:
            msg = f"indices length {len(indices)} does not match stack rows {stack.shape[0]}"
            raise ValueError(msg)

        peaks: list[Peak1D] = []
        for row, idx in zip(stack, indices):
            (peak,) = self._inner.execute(row, [int(idx)])
            peaks.append(peak)
        return peaks


class Interpolation2DNode:
    """Sub-sample position refinement for a list of 2D peak indices.

    Takes a list of ``(row, col)`` index tuples (e.g. from :class:`LocalMaxima2DNode`)
    and refines each to a physical position on the provided axis grids. Also populates
    amplitude from the data array.
    """

    def __init__(
        self,
        axis0_grid: _NDf64,
        axis1_grid: _NDf64,
        method: InterpolationMethod2D = InterpolationMethod2D.GAUSSIAN_INDEPENDENT,
        radius: tuple[int, int] = (1, 1),
    ) -> None:
        """
        :param axis0_grid: Physical values for rows, shape ``(R,)``. ``execute`` validates
            the input data shape against this.
        :param axis1_grid: Physical values for cols, shape ``(C,)``. ``execute`` validates
            the input data shape against this.
        :param method: Sub-sample refinement method.
        :param radius: Half-width in pixels ``(axis0, axis1)`` of the interpolation window.
            ``GAUSSIAN`` with ``radius=1`` on an axis uses the fast 3-point analytical
            formula; ``radius>1`` switches to least squares.
        """
        if axis0_grid.ndim != 1:
            msg = f"axis0_grid must be a 1D array, got shape {axis0_grid.shape}"
            raise ValueError(msg)
        if axis1_grid.ndim != 1:
            msg = f"axis1_grid must be a 1D array, got shape {axis1_grid.shape}"
            raise ValueError(msg)
        self._axis0_grid = axis0_grid
        self._axis1_grid = axis1_grid
        self._method = method
        self._radius = radius

    def execute(
        self,
        data: _NDf64,
        indices: list[tuple[int, int]],
    ) -> list[Peak2D]:
        """Refine a list of integer peak indices to physical positions.

        :param data: 2D data array of shape ``(R, C)``, matching the configured axis lengths.
        :param indices: List of ``(row, col)`` integer index tuples.
        :returns: List of :class:`Peak2D` in the same order as ``indices``.
        """
        if data.ndim != 2:
            msg = f"data must be a 2D array, got shape {data.shape}"
            raise ValueError(msg)
        expected_shape = (len(self._axis0_grid), len(self._axis1_grid))
        if data.shape != expected_shape:
            msg = f"data must be a 2D array of shape {expected_shape}, got shape {data.shape}"
            raise ValueError(msg)

        peaks = [
            Peak2D(
                index=idx,
                amplitude=float(data[idx[0], idx[1]]),
                position=self._interpolate_at(data, idx),
            )
            for idx in indices
        ]
        return peaks

    def _interpolate_at(
        self,
        data: _NDf64,
        index: tuple[int, int],
    ) -> tuple[float, float]:
        """Refine the physical position of a single peak at the given integer index.

        :param data: 2D data array.
        :param index: ``(row, col)`` integer index of the peak.
        :returns: Refined ``(pos0, pos1)`` physical position.
        """
        R, C = data.shape
        r, c = index
        r_radius, c_radius = self._radius

        r_start = max(0, r - r_radius)
        r_end = min(R, r + r_radius + 1)
        c_start = max(0, c - c_radius)
        c_end = min(C, c + c_radius + 1)

        patch = data[r_start:r_end, c_start:c_end]
        row_start_rel = r_start - r
        col_start_rel = c_start - c

        row_offset, col_offset = self._interpolate_patch(patch, row_start_rel, col_start_rel)

        pos0 = _idx_to_val(self._axis0_grid, float(r) + row_offset)
        pos1 = _idx_to_val(self._axis1_grid, float(c) + col_offset)
        return pos0, pos1

    def _interpolate_patch(
        self,
        patch: _NDf64,
        row_start_rel: int,
        col_start_rel: int,
    ) -> tuple[float, float]:
        """Dispatch to the configured interpolation method."""
        rows, cols = patch.shape

        if rows == 1 and cols == 1:
            return 0.0, 0.0

        if self._method == InterpolationMethod2D.NONE:
            return 0.0, 0.0

        if self._method == InterpolationMethod2D.GAUSSIAN_INDEPENDENT:
            return self._gaussian_independent(patch, row_start_rel, col_start_rel)

        if self._method == InterpolationMethod2D.GAUSSIAN_2D:
            return self._gaussian_2d(patch, row_start_rel, col_start_rel)

        msg = f"Unknown interpolation method: {self._method!r}"
        raise ValueError(msg)

    def _gaussian_independent(
        self, patch: _NDf64, row_start_rel: int, col_start_rel: int
    ) -> tuple[float, float]:
        """Separable Gaussian: fit 1D Gaussian on each axis through the peak center.

        Uses the fast 3-point analytical formula for 3-element slices when the
        peak is centered at y[1] (interior slice) and log-domain least squares
        otherwise. The 3-point formula assumes the peak sits at the middle
        sample, which only holds when ``start_rel == -1``; boundary-clipped
        3-cell patches keep the centered peak elsewhere, so they must take the
        lstsq path.
        """
        rows, cols = patch.shape
        row_offset = 0.0
        col_offset = 0.0

        center_row_idx = -row_start_rel
        if 0 <= center_row_idx < rows:
            row_slice = patch[center_row_idx, :]
            if cols == 3 and col_start_rel == -1:
                col_offset = _gaussian_offset_1d(row_slice)
            else:
                col_offset = _gaussian_offset_lstsq(row_slice, col_start_rel)

        center_col_idx = -col_start_rel
        if 0 <= center_col_idx < cols:
            col_slice = patch[:, center_col_idx]
            if rows == 3 and row_start_rel == -1:
                row_offset = _gaussian_offset_1d(col_slice)
            else:
                row_offset = _gaussian_offset_lstsq(col_slice, row_start_rel)

        return row_offset, col_offset

    def _gaussian_2d(
        self,
        patch: _NDf64,
        row_start_rel: int,
        col_start_rel: int,
    ) -> tuple[float, float]:
        """True 2D Gaussian surface fit via least squares.

        Fits: ln f(r,c) = c0 + p*r + q*c + alpha*r^2 + beta*c^2 + gamma*r*c
        where r, c are coordinates relative to the peak. Non-positive pixels
        (including threshold-masked zeros) are excluded from the lstsq system.

        Falls back to GAUSSIAN_INDEPENDENT if fewer than 6 valid pixels remain
        or the system is near-singular.
        """
        rows, cols = patch.shape
        r_center = -row_start_rel
        c_center = -col_start_rel

        M = np.empty((rows * cols, 6), dtype=np.float64)
        k = 0
        for i in range(rows):
            for j in range(cols):
                r = float(i - r_center)
                c = float(j - c_center)
                M[k] = [1.0, r, c, r * r, c * c, r * c]
                k += 1

        p_flat = patch.ravel()
        valid = p_flat > _NEAR_ZERO
        if np.sum(valid) < 6:
            return self._gaussian_independent(patch, row_start_rel, col_start_rel)

        z = np.log(p_flat[valid])
        theta, _, _, _ = np.linalg.lstsq(M[valid], z, rcond=None)
        p, q, alpha, beta, gamma = theta[1], theta[2], theta[3], theta[4], theta[5]

        # Vertex of f(r,c) = c0 + p*r + q*c + alpha*r^2 + beta*c^2 + gamma*r*c
        # solves [[2*alpha, gamma], [gamma, 2*beta]] @ [r, c]^T = [-p, -q]^T.
        det = 4.0 * alpha * beta - gamma * gamma
        if abs(det) < _NEAR_ZERO:
            return self._gaussian_independent(patch, row_start_rel, col_start_rel)

        row_offset = float(np.clip((q * gamma - 2.0 * p * beta) / det, -0.5, 0.5))
        col_offset = float(np.clip((p * gamma - 2.0 * alpha * q) / det, -0.5, 0.5))
        return row_offset, col_offset
