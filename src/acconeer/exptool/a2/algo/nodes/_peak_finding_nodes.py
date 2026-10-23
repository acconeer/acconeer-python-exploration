# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt
from scipy.ndimage import maximum_filter


_NDf64 = npt.NDArray[np.float64]


class LocalMaxima1DNode:
    """Finds local maxima in a 1D signal via a sliding ``maximum_filter`` window.

    A cell is reported as a local maximum if its value equals the maximum within a
    window of half-width ``radius`` centered on it (window size ``2 * radius + 1``).
    Boundary cells use ``mode="constant"`` with fill value ``-inf``, so they
    effectively only compete against the available interior neighbors.

    The ``data == maximum_filter(data)`` comparison is non-strict: tied adjacent
    cells both qualify, and **every cell in a fully-uniform region also qualifies**
    (every cell equals its window's local max). This includes a flat-zero
    background or a single-cell array — both produce "peaks" everywhere.
    Downstream deduplication (e.g. ``Peak3DCartXYNMSNode``) and/or a threshold
    above the noise floor (e.g. from CFAR) are expected to filter these out.

    Callers should handle NaN before calling: NaN propagates through the filter
    and produces unspecified results.

    Returns all local maxima above threshold as integer indices.
    """

    def __init__(self, radius: int = 1) -> None:
        """
        :param radius: Half-width of the search window in cells. Window size is
            ``2 * radius + 1``. Default ``1`` reproduces the previous immediate-neighbor
            behavior; larger values widen the suppression neighborhood and are typically
            chosen to match the expected peak FWHM in cells.
        """
        if radius < 1:
            msg = f"radius must be at least 1, got {radius}."
            raise ValueError(msg)
        self._radius = radius

    def execute(
        self,
        data: _NDf64,
        threshold: t.Union[float, _NDf64] = -np.inf,
    ) -> list[int]:
        """Find all local maxima in a 1D data array.

        :param data: 1D array of shape ``(n,)``.
        :param threshold: Scalar or 1D array of shape ``(n,)`` with minimum data values.
            Candidates strictly below their threshold are ignored.
        :returns: List of integer indices of local maxima, in ascending index order.
        """
        if data.ndim != 1:
            msg = f"data must be a 1D array, got shape {data.shape}"
            raise ValueError(msg)

        n = len(data)
        thr = np.asarray(threshold, dtype=np.float64)
        if thr.ndim == 0:
            threshold_arr = np.broadcast_to(thr, (n,))
        elif thr.shape == (n,):
            threshold_arr = thr
        else:
            msg = (
                f"threshold must be a scalar or a 1D array of shape {(n,)}, got shape {thr.shape}"
            )
            raise ValueError(msg)

        size = (2 * self._radius + 1,)
        local_max = maximum_filter(data, size=size, mode="constant", cval=-np.inf)
        mask = (data == local_max) & (data >= threshold_arr)
        return [int(i) for i in np.argwhere(mask).ravel()]


class LocalMaxima2DNode:
    """Finds local maxima in a 2D signal via a sliding ``maximum_filter`` window.

    A cell is reported as a local maximum if its value equals the maximum within a
    rectangular window of half-widths ``radii`` centered on it (window shape
    ``(2*radii[0]+1, 2*radii[1]+1)``). Boundary cells use ``mode="constant"``
    with fill value ``-inf``, so they effectively only compete against the
    available interior neighbors.

    The ``data == maximum_filter(data)`` comparison is non-strict: tied adjacent
    cells both qualify, and **every cell in a fully-uniform region also qualifies**
    (every cell equals its window's local max). This includes flat-zero
    backgrounds in heatmaps. Downstream deduplication (e.g.
    ``Peak3DCartXYNMSNode``) and/or a threshold above the noise floor (e.g. from
    CFAR) are expected to filter these out.

    Callers should handle NaN before calling: NaN propagates through the filter
    and produces unspecified results.

    Returns all local maxima above threshold as a list of ``(row, col)`` index tuples.
    """

    def __init__(
        self,
        radii: t.Tuple[int, int] = (1, 1),
    ) -> None:
        """
        :param radii: Half-widths ``(axis0, axis1)`` of the search window in cells.
            Window shape is ``(2*radii[0]+1, 2*radii[1]+1)``. Default ``(1, 1)``
            reproduces the previous 8-connectivity immediate-neighbor behavior;
            larger values widen the suppression neighborhood per axis and are typically
            chosen to match the expected peak FWHM in cells on each axis.
        """
        if any(r < 1 for r in radii):
            msg = f"radii entries must each be at least 1, got {radii}."
            raise ValueError(msg)
        self._radii = radii

    def execute(
        self,
        data: _NDf64,
        threshold: t.Union[float, _NDf64] = -np.inf,
    ) -> list[tuple[int, int]]:
        """Find all local maxima in a 2D data array.

        :param data: 2D array of shape ``(n_rows, n_cols)``.
        :param threshold: Scalar or 2D array ``(n_rows, n_cols)`` of minimum values.
        :returns: List of ``(row, col)`` integer index tuples of local maxima, in
            row-major order.
        """
        if data.ndim != 2:
            msg = f"data must be a 2D array, got shape {data.shape}"
            raise ValueError(msg)
        n_rows, n_cols = data.shape
        thr = np.asarray(threshold, dtype=np.float64)
        if thr.ndim == 0:
            threshold_arr = np.broadcast_to(thr, (n_rows, n_cols))
        elif thr.shape == (n_rows, n_cols):
            threshold_arr = thr
        else:
            msg = (
                f"threshold must be a scalar or a 2D array of shape {(n_rows, n_cols)}, "
                f"got shape {thr.shape}"
            )
            raise ValueError(msg)

        size = (2 * self._radii[0] + 1, 2 * self._radii[1] + 1)
        local_max = maximum_filter(data, size=size, mode="constant", cval=-np.inf)
        mask = (data == local_max) & (data >= threshold_arr)
        return [(int(r), int(c)) for r, c in np.argwhere(mask)]
