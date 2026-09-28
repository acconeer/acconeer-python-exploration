# Copyright (c) Acconeer AB, 2026
# All rights reserved
"""Angle-dependent correction to :data:`MEAN_BASE_RLG_DB
<acconeer.exptool.a2.algo._utils.MEAN_BASE_RLG_DB>`, capturing the AP212
antenna element's radar loop gain falloff off boresight.

The packaged grid (``_rlg_correction_grid.py``) was generated OFFLINE
from raw characterization measurements (not part of this package).
"""

from __future__ import annotations

import functools

import numpy as np
import numpy.typing as npt

from ._rlg_correction_grid import AZ_DEG, CORRECTION_DB, EL_DEG


@functools.cache
def _load_grid() -> tuple[
    npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]
]:
    """``(az_deg, el_deg, correction_db)``, loaded once. ``correction_db``
    has shape ``(len(el_deg), len(az_deg))``, i.e. ``correction_db[i, j]`` is
    the value at ``(az_deg[j], el_deg[i])``."""
    az_deg = np.asarray(AZ_DEG, dtype=np.float64)
    el_deg = np.asarray(EL_DEG, dtype=np.float64)
    correction_db = np.asarray(CORRECTION_DB, dtype=np.float64)
    return az_deg, el_deg, correction_db


@functools.cache
def measured_az_range_deg() -> tuple[float, float]:
    """``(lo, hi)`` azimuth range the packaged grid was actually characterized over."""
    az_deg, _, _ = _load_grid()
    return float(az_deg[0]), float(az_deg[-1])


@functools.cache
def measured_el_range_deg() -> tuple[float, float]:
    """``(lo, hi)`` elevation range the packaged grid was actually characterized over."""
    _, el_deg, _ = _load_grid()
    return float(el_deg[0]), float(el_deg[-1])


def is_within_measured_envelope(
    az_deg: npt.ArrayLike, el_deg: npt.ArrayLike
) -> npt.NDArray[np.bool_]:
    """Elementwise: does ``(az_deg, el_deg)`` fall within the packaged grid's
    characterized envelope? Values outside it are still evaluable (see
    :func:`rlg_correction_db`), but callers that care about being outside
    the characterized region, e.g. to raise a ``ValidationWarning``,
    should check this first."""
    az_lo, az_hi = measured_az_range_deg()
    el_lo, el_hi = measured_el_range_deg()
    az = np.asarray(az_deg, dtype=np.float64)
    el = np.asarray(el_deg, dtype=np.float64)
    return (az >= az_lo) & (az <= az_hi) & (el >= el_lo) & (el <= el_hi)


def _bilinear_interp(
    x_grid: npt.NDArray[np.float64],
    y_grid: npt.NDArray[np.float64],
    z_grid: npt.NDArray[np.float64],
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Bilinear interpolation of ``z_grid`` (shape ``(len(y_grid), len(x_grid))``)
    at ``(x, y)``. Outside the grid's own range, clamps ``tx``/``ty`` to
    ``[0, 1]`` instead of extrapolating, so the result is always a convex
    combination of the cell's four corner values: bounded within the
    grid's own min/max, never a computed guess. ``x_grid``/``y_grid`` must
    be sorted ascending."""
    xi = np.clip(np.searchsorted(x_grid, x, side="right") - 1, 0, len(x_grid) - 2)
    yi = np.clip(np.searchsorted(y_grid, y, side="right") - 1, 0, len(y_grid) - 2)

    x0, x1 = x_grid[xi], x_grid[xi + 1]
    y0, y1 = y_grid[yi], y_grid[yi + 1]
    tx = np.clip((x - x0) / (x1 - x0), 0.0, 1.0)
    ty = np.clip((y - y0) / (y1 - y0), 0.0, 1.0)

    z00 = z_grid[yi, xi]
    z01 = z_grid[yi, xi + 1]
    z10 = z_grid[yi + 1, xi]
    z11 = z_grid[yi + 1, xi + 1]

    result = z00 * (1 - tx) * (1 - ty) + z01 * tx * (1 - ty) + z10 * (1 - tx) * ty + z11 * tx * ty
    return result


@functools.cache
def _fit_global_quadratic() -> npt.NDArray[np.float64]:
    """Least-squares coefficients ``(c0, c1, c2, c3, c4, c5)`` of
    ``c0 + c1*az + c2*el + c3*az**2 + c4*az*el + c5*el**2``, fit once to the
    whole packaged grid. Antenna gain patterns are commonly approximated as
    parabolic (in dB) near the main lobe; fitting every point at once means
    no single noisy measurement can steer the result."""
    az_grid, el_grid, correction_db = _load_grid()
    az_mesh, el_mesh = np.meshgrid(az_grid, el_grid, indexing="xy")
    az_flat, el_flat = az_mesh.ravel(), el_mesh.ravel()
    design = np.stack(
        [np.ones_like(az_flat), az_flat, el_flat, az_flat**2, az_flat * el_flat, el_flat**2],
        axis=1,
    )
    coeffs, *_ = np.linalg.lstsq(design, correction_db.ravel(), rcond=None)
    return coeffs


def _quadratic_correction_db(
    az_deg: npt.NDArray[np.float64], el_deg: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Evaluates :func:`_fit_global_quadratic`'s surface at ``(az_deg, el_deg)``.
    Unlike :func:`_bilinear_interp`, it is defined and unbounded everywhere."""
    c0, c1, c2, c3, c4, c5 = _fit_global_quadratic()
    result = (
        c0 + c1 * az_deg + c2 * el_deg + c3 * az_deg**2 + c4 * az_deg * el_deg + c5 * el_deg**2
    )
    return result  # type: ignore[no-any-return]


# Degrees inward from each edge of the characterized envelope over which
# rlg_correction_db smoothstep-blends from the measured grid to the global
# quadratic fit (see _fit_global_quadratic), so the transition has no jump
# or kink right at the envelope boundary.
_BLEND_MARGIN_DEG = 10.0


def _smoothstep(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Standard cubic (Hermite) smoothstep: 0 for ``x <= 0``, 1 for
    ``x >= 1``, an S-curve with zero slope at both ends in between."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _blend_weight(
    az_deg: npt.NDArray[np.float64], el_deg: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """0 more than ``_BLEND_MARGIN_DEG`` inside either envelope edge (pure
    measured grid); 1 at and beyond the edge (pure quadratic fit);
    smoothstepped over that margin in between."""
    az_lo, az_hi = measured_az_range_deg()
    el_lo, el_hi = measured_el_range_deg()
    az_depth = np.maximum(az_lo + _BLEND_MARGIN_DEG - az_deg, az_deg - (az_hi - _BLEND_MARGIN_DEG))
    el_depth = np.maximum(el_lo + _BLEND_MARGIN_DEG - el_deg, el_deg - (el_hi - _BLEND_MARGIN_DEG))
    depth = np.maximum(np.maximum(az_depth, el_depth), 0.0)
    return _smoothstep(depth / _BLEND_MARGIN_DEG)


def rlg_correction_db(az_deg: npt.ArrayLike, el_deg: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Additive dB correction to ``MEAN_BASE_RLG_DB[profile]`` at the given
    raw-frame ``(az_deg, el_deg)``. Bilinear interpolation over the packaged grid
    within the characterized envelope (:func:`is_within_measured_envelope`);
    starting ``_BLEND_MARGIN_DEG`` before the envelope edge, smoothstep-blends
    into a global quadratic surface fit to the whole grid (see
    :func:`_fit_global_quadratic`), reaching 100% quadratic at and beyond the
    edge. This keeps the correction smooth and well-behaved arbitrarily far
    past the characterized region.

    Includes both the angular falloff shape and a fixed 5th-percentile safety
    margin. Because of that margin, this is *not* 0.0 dB at boresight, but a
    small negative number, since the margin applies at every angle.

    Assumption: the angular falloff shape is profile- and distance-independent
    (a property of the antenna element's physical gain pattern, not the
    chirp), as the underlying characterization data was only measured at one
    profile and one distance.
    """
    az_grid, el_grid, correction_db = _load_grid()
    az = np.asarray(az_deg, dtype=np.float64)
    el = np.asarray(el_deg, dtype=np.float64)

    measured = _bilinear_interp(az_grid, el_grid, correction_db, az, el)
    fitted = _quadratic_correction_db(az, el)
    weight = _blend_weight(az, el)
    result = (1.0 - weight) * measured + weight * fitted
    return result[()] if result.ndim == 0 else result
