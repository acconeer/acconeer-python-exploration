# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t
import warnings
from enum import Enum

import attrs
import attrs.validators as av
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a2
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from acconeer.exptool.a2.algo._detection_geometry import (
    DetectionVolume,
    SensorInstallation,
)
from acconeer.exptool.a2.algo._shared_config import (
    MAX_RANGE_M,
    WallMountSessionAbstractionConfig,
    room_z_bounds_m,
)
from acconeer.exptool.a2.algo._utils import (
    BASE_STEP_LENGTH_M,
    CONVENTIONAL_AZ_FWHM_DEG,
    ENVELOPE_FWHM_M,
    ENVELOPE_LENGTH_M,
)
from acconeer.exptool.a2.algo.nodes._cfar_subnodes import CFARAggregateMethod, CFARKernelType
from acconeer.exptool.a2.algo.nodes._peak_interpolation_nodes import InterpolationMethod2D


class BeamformingMethod(str, Enum):
    CAPON = "CAPON"
    ROBUST_CAPON = "ROBUST_CAPON"


class HeatmapDisplayMode(str, Enum):
    HEATMAP_MASKED = "HEATMAP_MASKED"
    HEATMAP_ON = "HEATMAP_ON"
    HEATMAP_OFF = "HEATMAP_OFF"


def _to_aggregate_methods(
    v: t.Iterable[t.Any],
) -> tuple[CFARAggregateMethod, CFARAggregateMethod]:
    a, b = (CFARAggregateMethod(m) for m in v)
    return a, b


def _to_float_pair(v: t.Iterable[float]) -> tuple[float, float]:
    a, b = v
    return float(a), float(b)


def _to_optional_float_pair(
    v: t.Iterable[float] | None,
) -> tuple[float, float] | None:
    return None if v is None else _to_float_pair(v)


def _aggregate_methods_not_all_drop(
    instance: t.Any, attribute: t.Any, value: tuple[CFARAggregateMethod, CFARAggregateMethod]
) -> None:
    if all(m == CFARAggregateMethod.DROP for m in value):
        msg = (
            f"{attribute.name}: at least one axis must be non-DROP; "
            f"got ({value[0].name}, {value[1].name})."
        )
        raise ValueError(msg)


# Elevation interpolation half-width (cells). Requires
# ``2 * _N_EL_INTERPOLATION + 1`` el angles to fit; falls back to 0
# (no interpolation) when fewer angles are available.
_N_EL_INTERPOLATION = 1

# Maximum peak-finding half-width in cells (full window = 2*N + 1 bins).
# Distance: 2 → 5-bin window. Azimuth: 3 → 7-bin window (loosened so the
# default az_grid_resolution_deg=2.0 + 0.5 × FWHM factor lands exactly on the cap
# without triggering a warning).
_MAX_PEAK_FINDING_DIST_RADIUS_BINS = 2
_MAX_PEAK_FINDING_AZ_RADIUS_BINS = 3

# Endpoints of the log-linear map from ``cfar_sensitivity`` ∈ [0, 1] to the
# CA-CFAR theoretical false-positive rate.
_CFAR_FPR_MIN = 1e-8
_CFAR_FPR_MAX = 1.0


def _cells_from_deg(span_deg: float, num_angles: int, radius_deg: float) -> int:
    """Convert a degree radius into a cell-count half-width.

    Returns 0 when ``num_angles <= 1`` (single-cell axis, no neighbours exist).
    Otherwise rounds the requested radius to the nearest cell, with a floor of
    1 when the user asks for a non-zero radius.
    """
    if num_angles <= 1:
        return 0
    step_deg = span_deg / (num_angles - 1)
    n = int(round(radius_deg / step_deg))
    if radius_deg > 0 and n < 1:
        n = 1
    return n


def _cells_from_length(
    reference_length_m: float,
    step_length_m: float,
    factor: float,
) -> int:
    """Convert a length factor into a distance cell-count half-width.

    ``reference_length_m`` is the physical length the factor is relative to —
    e.g. profile length for CFAR (leakage region) or envelope FWHM for peak
    interpolation. Callers should clamp the result to ``(num_points - 1) // 2``
    to handle single-cell grids.
    """
    n = round(factor * reference_length_m / step_length_m)
    if factor > 0 and n < 1:
        n = 1
    return n


def _compute_cfar_radii(
    az_span: float,
    num_az_angles: int,
    profile: a2.Profile,
    step_length_m: float,
    num_points: int,
    az_guard_fwhm_factor: float,
    dist_guard_envelope_len_factor: float,
    az_reference_fwhm_factor: float,
    dist_reference_envelope_len_factor: float,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Convert physical guard/reference parameters into ``(distance, azimuth)`` cell counts.

    Distance factors are relative to ``ENVELOPE_LENGTH_M[profile]``; azimuth
    factors are relative to ``CONVENTIONAL_AZ_FWHM_DEG``. Radii are clamped to
    ``(grid_size - 1) // 2`` so a mismatched config pair (large factor against
    a small grid) cannot push CFAR past the heatmap edges.

    :returns: ``(guard_radii, ref_radii)`` — each a ``(distance, azimuth)`` tuple of cells.
    """
    max_az = max(0, (num_az_angles - 1) // 2)
    max_d = max(0, (num_points - 1) // 2)
    envelope_len_m = ENVELOPE_LENGTH_M[profile]
    n_guard_d = min(
        _cells_from_length(envelope_len_m, step_length_m, dist_guard_envelope_len_factor), max_d
    )
    n_ref_d = min(
        _cells_from_length(envelope_len_m, step_length_m, dist_reference_envelope_len_factor),
        max_d,
    )
    az_guard_deg = az_guard_fwhm_factor * CONVENTIONAL_AZ_FWHM_DEG
    az_reference_deg = az_reference_fwhm_factor * CONVENTIONAL_AZ_FWHM_DEG
    n_guard_az = min(_cells_from_deg(az_span, num_az_angles, az_guard_deg), max_az)
    n_ref_az = min(_cells_from_deg(az_span, num_az_angles, az_reference_deg), max_az)
    return (n_guard_d, n_guard_az), (n_ref_d, n_ref_az)


def _sensitivity_to_fpr(sensitivity: float) -> float:
    """Map sensitivity in [0, 1] to a CA-CFAR target false-positive rate (log-linear).

    ``sensitivity = 0`` -> FPR = ``_CFAR_FPR_MIN`` (strictest).
    ``sensitivity = 1`` -> FPR = ``_CFAR_FPR_MAX`` (loosest, no CFAR threshold).
    """
    log_fpr = np.log(_CFAR_FPR_MIN) + sensitivity * (np.log(_CFAR_FPR_MAX) - np.log(_CFAR_FPR_MIN))
    return float(np.exp(log_fpr))


def _compute_peak_finding_radii(
    az_span: float,
    num_az_angles: int,
    profile: a2.Profile,
    step_length_m: float,
    num_points: int,
    peak_finding_dist_radius_fwhm_factor: float,
    peak_finding_az_radius_fwhm_factor: float,
) -> tuple[int, int]:
    """Convert FWHM-relative peak-finding radii into distance and azimuth cell counts.

    The same ``(n_dist, n_az)`` half-widths are used both as the ``LocalMaxima2DNode``
    search window and as the ``Interpolation2DNode`` fitting window. Both nodes
    benefit from a footprint sized to the expected peak FWHM.

    The distance factor is relative to ``ENVELOPE_FWHM_M[profile]``; the
    azimuth factor is relative to ``CONVENTIONAL_AZ_FWHM_DEG``
    (an upper bound for Capon / robust-Capon variants).

    Each axis is clamped to ``min(half the grid size, _MAX_PEAK_FINDING_*_RADIUS_BINS)``.
    Elevation is handled separately via ``_N_EL_INTERPOLATION``.

    :returns: ``(n_dist, n_az)`` — peak-finding half-widths in cells.
    """
    max_az = max(0, (num_az_angles - 1) // 2)
    max_d = max(0, (num_points - 1) // 2)
    fwhm_m = ENVELOPE_FWHM_M[profile]
    n_dist = min(
        _cells_from_length(fwhm_m, step_length_m, peak_finding_dist_radius_fwhm_factor),
        max_d,
        _MAX_PEAK_FINDING_DIST_RADIUS_BINS,
    )
    radius_deg = peak_finding_az_radius_fwhm_factor * CONVENTIONAL_AZ_FWHM_DEG
    n_az = min(
        _cells_from_deg(az_span, num_az_angles, radius_deg),
        max_az,
        _MAX_PEAK_FINDING_AZ_RADIUS_BINS,
    )
    return n_dist, n_az


@attributes_doc
@attrs.mutable
class MotionDetectionConfig(AttrsMappingTransformsMixin):
    antenna_array: a2.AntennaArray = attrs.field(converter=a2.AntennaArray)
    """The antenna layout for the sensor used."""

    beamforming_method: BeamformingMethod = attrs.field(
        default=BeamformingMethod.ROBUST_CAPON,
        converter=BeamformingMethod,
    )
    """Will set the beamforming method used. See BeamformingMethod class."""

    robust_capon_epsilon: float = attrs.field(default=0.1, validator=[av.gt(0.0), av.le(1.0)])
    """Steering-vector loading factor for the robust Capon beamformer if used."""

    covariance_matrix_time_constant_s: float = attrs.field(default=0.0, validator=av.ge(0.0))
    """Time constant for IIR low-pass filter of the covariance matrices."""

    high_pass_filter_time_constant_s: float = attrs.field(default=5.0, validator=av.ge(0.0))
    """Time constant for the IIR high-pass filter of the IQ data."""

    spatial_high_pass_filter_time_constant_s: float = attrs.field(
        default=5.0, validator=av.gt(0.0)
    )
    """Time constant for the IIR spatial high-pass filter used to suppress static clutter"""

    jitter_averaging_efficiency: float = attrs.field(
        default=0.7, validator=[av.gt(0.0), av.le(1.0)]
    )
    """Effective averaging efficiency for correlated jitter. Empirical default
    is 0.7 (see ``JitterAndVibrationScalingNode``)."""

    spatial_uncorr_jitter_factor: float = attrs.field(
        default=0.1, validator=[av.ge(0.0), av.le(1.0)]
    )
    """Fraction of jitter assumed spatially uncorrelated across channels."""

    az_angle_range: tuple[float, float] | None = attrs.field(
        default=None,
        converter=_to_optional_float_pair,
        validator=av.optional([av.min_len(2), av.max_len(2)]),
    )
    """Min and max az angle (degrees), overriding the detection volume's own
    ``az_angle_range`` for this processor. ``None`` uses the detection
    volume's value unmodified."""

    el_angle_range: tuple[float, float] | None = attrs.field(
        default=None,
        converter=_to_optional_float_pair,
        validator=av.optional([av.min_len(2), av.max_len(2)]),
    )
    """Min and max el angle (degrees), overriding the detection volume's own
    ``el_angle_range`` for this processor. ``None`` uses the detection
    volume's value unmodified. Ignored when :py:attr:`el_grid_resolution_deg`
    is ``None``."""

    az_grid_resolution_deg: float = attrs.field(
        default=2.0, validator=[av.gt(0.0), av.le(CONVENTIONAL_AZ_FWHM_DEG)]
    )
    """Desired azimuth grid resolution in degrees. The actual resolution is
    rounded to the nearest value that produces an integer number of bins
    across the effective az angle range; inspect :py:meth:`num_az_angles` or
    :py:meth:`az_angles` to see the resulting grid."""

    el_grid_resolution_deg: float | None = attrs.field(
        default=15.0,
        validator=av.optional(av.gt(0.0)),  # type: ignore[arg-type]
    )
    """Desired elevation grid resolution in degrees. ``None`` collapses the
    el grid to a single boresight point at ``el = 0°`` (and ignores
    :py:attr:`el_angle_range`)."""

    vibration_std_um: float = attrs.field(default=0.0, validator=[av.ge(0.0), av.le(100.0)])
    """Standard deviation of sensor vibration in micrometres for jitter/vibration compensation."""

    # --- CFAR ---
    cfar_kernel_type: CFARKernelType = attrs.field(
        default=CFARKernelType.THICK_CROSS,
        converter=CFARKernelType,
    )
    """
    THIN_CROSS: Standard cross with single-bin width arms.
    THICK_CROSS: Wider cross where arm width matches the guard width.
    """

    cfar_aggregate_method: tuple[CFARAggregateMethod, CFARAggregateMethod] = attrs.field(
        default=(CFARAggregateMethod.GO, CFARAggregateMethod.SO),
        converter=_to_aggregate_methods,
        validator=_aggregate_methods_not_all_drop,
    )
    """Per-axis arm aggregation ``(distance, azimuth)``. Each entry is an
    ``CFARAggregateMethod`` (``CA``/``GO``/``SO``/``DROP``); ``DROP`` skips
    that axis. At least one entry must be non-``DROP``.

    Common combinations:

    * ``(CA, CA)`` — cell-average all four arms (standard CA-CFAR).
    * ``(GO, SO)`` — greatest-of on distance, smallest-of on azimuth.
    * ``(DROP, CA)`` — average azimuth arms only (no distance arms).
    """

    cfar_az_guard_fwhm_factor: float = attrs.field(
        default=0.78, validator=[av.ge(0.0), av.le(2.0)]
    )
    """Guard interval in Azimuth as a multiple of ``CONVENTIONAL_AZ_FWHM_DEG``.
    Factor > 1 is allowed since CFAR guards should reach past the main lobe."""

    cfar_dist_guard_envelope_len_factor: float = attrs.field(default=0.5, validator=[av.ge(0.0)])
    """Guard interval in Distance as a factor of the pulse envelope length."""

    cfar_az_reference_fwhm_factor: float = attrs.field(
        default=0.78, validator=[av.gt(0.0), av.le(2.0)]
    )
    """Reference window size in Azimuth as a multiple of ``CONVENTIONAL_AZ_FWHM_DEG``.
    Factor > 1 is allowed for the same reason as the guard factor."""

    cfar_dist_reference_envelope_len_factor: float = attrs.field(
        default=0.5, validator=[av.gt(0.0)]
    )
    """Reference window size in Distance as a factor of the pulse envelope length."""

    cfar_sensitivity: float = attrs.field(default=0.75, validator=[av.ge(0.0), av.le(1.0)])
    """Sensitivity of the CFAR threshold. High sensitivity equals low detection
    threshold, low sensitivity equals high detection threshold. The processor maps
    this log-linearly onto a theoretical per-pixel false-positive rate."""

    cfar_fixed_threshold: float = attrs.field(default=1.0, validator=av.ge(0.0))
    """Hard lower bound on the CFAR threshold map, in heatmap units. The
    noise-normalisation pipeline divides the IQ frame by the noise floor so
    the thermal-noise mean at the beamformer output is ≈ 1; raising this
    above 1 implements the absolute-floor term that some classical CFAR
    formulations write as ``thermal_mean + N·σ_thermal``."""

    cfar_side_lobe_compensation_db: float | None = attrs.field(
        default=-10.0,
        validator=av.optional(av.le(0.0)),  # type: ignore[arg-type]
    )
    """Limit threshold relative to the per-range-bin peak by this value (dB).
    Set to None to disable."""

    # --- Peak finding ---
    peak_min_dist_separation_m: float = attrs.field(default=0.2, validator=[av.ge(0.0)])
    """Minimum Cartesian separation between retained peaks in the az-dist plane."""

    peak_interpolation_az_dist_method: InterpolationMethod2D = attrs.field(
        default=InterpolationMethod2D.GAUSSIAN_INDEPENDENT,
        converter=InterpolationMethod2D,
    )
    """Interpolation method for peak position refinement in the (azimuth, distance) plane."""

    peak_finding_dist_radius_fwhm_factor: float = attrs.field(
        default=0.5, validator=[av.gt(0.0), av.le(1.0)]
    )
    """Peak-finding half-width along distance as a multiple of the measured
    envelope FWHM (``ENVELOPE_FWHM_M``). Sizes both the ``LocalMaxima2DNode``
    search window and the ``Interpolation2DNode`` fitting window."""

    peak_finding_az_radius_fwhm_factor: float = attrs.field(
        default=0.5, validator=[av.gt(0.0), av.le(1.0)]
    )
    """Peak-finding half-width along azimuth as a multiple of the conventional
    beamformer's azimuth FWHM (``CONVENTIONAL_AZ_FWHM_DEG``). Sizes both the
    ``LocalMaxima2DNode`` search window and the ``Interpolation2DNode`` fitting
    window. Conventional beamforming defines the FWHM; for Capon / robust Capon
    the main lobe is narrower so this serves as a loose upper bound."""

    # --- Detection volume overrides ---
    # The detection volume defines the physical area the sensor covers;
    # these let this processor narrow, widen, or opt out of that area on a
    # per-axis basis without changing the shared DetectionVolume.
    detection_volume_x_bound_offset_m: tuple[float, float] | None = attrs.field(
        default=None, converter=_to_optional_float_pair
    )
    """``(lo, hi)`` offset in metres added to the detection volume's
    ``x_bounds_m`` to get this processor's actual x bound, or ``None`` for
    no box bound in x (unbounded on that axis for this processor,
    independent of the detection volume). Without a box in the detection
    volume, this processor has no bound on that axis either."""

    detection_volume_y_bound_offset_m: tuple[float, float] | None = attrs.field(
        default=None, converter=_to_optional_float_pair
    )
    """``(lo, hi)`` offset in metres added to the detection volume's
    ``y_bounds_m`` to get this processor's actual y bound, or ``None`` for
    no box bound in y (unbounded on that axis for this processor,
    independent of the detection volume). Without a box in the detection
    volume, this processor has no bound on that axis either."""

    detection_volume_z_bound_offset_m: tuple[float, float] | None = attrs.field(
        default=None, converter=_to_optional_float_pair
    )
    """``(lo, hi)`` offset in metres added to the room's height (see
    ``room_z_bounds_m``) to get this processor's actual z bound, or ``None`` for
    no box bound in z (unbounded on that axis for this processor,
    independent of the detection volume). Without a box in the detection
    volume, this processor has no bound on that axis either."""

    def to_dict(self) -> dict[str, t.Any]:
        # Don't recurse into nested attrs classes — ``antenna_array`` is an
        # attrs+Enum hybrid; recursing expands it into its full geometry.
        return attrs.asdict(self, recurse=False)

    def effective_az_angle_range(self, detection_volume: DetectionVolume) -> tuple[float, float]:
        return (
            self.az_angle_range
            if self.az_angle_range is not None
            else detection_volume.az_angle_range
        )

    def effective_el_angle_range(self, detection_volume: DetectionVolume) -> tuple[float, float]:
        return (
            self.el_angle_range
            if self.el_angle_range is not None
            else detection_volume.el_angle_range
        )

    @staticmethod
    def _offset_bound(
        offset: tuple[float, float] | None,
        detection_volume_bound: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        if offset is None or detection_volume_bound is None:
            return None
        return detection_volume_bound[0] + offset[0], detection_volume_bound[1] + offset[1]

    def effective_x_bounds_m(
        self, detection_volume: DetectionVolume
    ) -> tuple[float, float] | None:
        """This processor's x bound: ``None`` (unbounded) if
        :py:attr:`detection_volume_x_bound_offset_m` or the detection
        volume's ``x_bounds_m`` is ``None``, else the latter offset by
        the former."""
        return self._offset_bound(
            self.detection_volume_x_bound_offset_m, detection_volume.x_bounds_m
        )

    def effective_y_bounds_m(
        self, detection_volume: DetectionVolume
    ) -> tuple[float, float] | None:
        """This processor's y bound: ``None`` (unbounded) if
        :py:attr:`detection_volume_y_bound_offset_m` or the detection
        volume's ``y_bounds_m`` is ``None``, else the latter offset by
        the former."""
        return self._offset_bound(
            self.detection_volume_y_bound_offset_m, detection_volume.y_bounds_m
        )

    def effective_z_bounds_m(
        self, sensor_installation: SensorInstallation, detection_volume: DetectionVolume
    ) -> tuple[float, float] | None:
        """This processor's z bound: ``None`` (unbounded) if
        :py:attr:`detection_volume_z_bound_offset_m` is ``None`` or the
        detection volume has no box, else the room's height (see
        ``room_z_bounds_m``) offset by the former."""
        if detection_volume.x_bounds_m is None or detection_volume.y_bounds_m is None:
            return None
        return self._offset_bound(
            self.detection_volume_z_bound_offset_m, room_z_bounds_m(sensor_installation)
        )

    @staticmethod
    def _get_angles(num: int, angle_range: tuple[float, float]) -> npt.NDArray[np.float64]:
        if num == 1:
            midpoint = (angle_range[0] + angle_range[1]) / 2.0
            return np.array([midpoint])
        return np.linspace(
            start=angle_range[0], stop=angle_range[1], num=num, endpoint=True, dtype=np.float64
        )

    @staticmethod
    def _num_from_resolution(angle_range: tuple[float, float], resolution_deg: float) -> int:
        """Round ``span / resolution`` to the nearest integer number of bins.

        ``num_angles = n_intervals + 1`` with ``n_intervals >= 1`` whenever the
        span is non-zero, so a non-degenerate range always yields at least two
        grid points (endpoints). Degenerate ranges (``span == 0``) short-
        circuit to a single point.
        """
        span = angle_range[1] - angle_range[0]
        if span == 0:
            return 1
        n_intervals = max(1, round(span / resolution_deg))
        return n_intervals + 1

    def num_az_angles(self, detection_volume: DetectionVolume) -> int:
        """Number of azimuth bins, derived from
        :py:attr:`az_grid_resolution_deg` and the effective az angle range."""
        return self._num_from_resolution(
            self.effective_az_angle_range(detection_volume), self.az_grid_resolution_deg
        )

    def num_el_angles(self, detection_volume: DetectionVolume) -> int:
        """Number of elevation bins, derived from
        :py:attr:`el_grid_resolution_deg` and the effective el angle range.
        Returns ``1`` when ``el_grid_resolution_deg`` is ``None``."""
        if self.el_grid_resolution_deg is None:
            return 1
        return self._num_from_resolution(
            self.effective_el_angle_range(detection_volume), self.el_grid_resolution_deg
        )

    def az_angles(self, detection_volume: DetectionVolume) -> npt.NDArray[np.float64]:
        """The az angles defined by this config."""
        return self._get_angles(
            self.num_az_angles(detection_volume),
            self.effective_az_angle_range(detection_volume),
        )

    def el_angles(self, detection_volume: DetectionVolume) -> npt.NDArray[np.float64]:
        """The el angles defined by this config. Returns ``[0.0]`` when
        :py:attr:`el_grid_resolution_deg` is ``None``."""
        if self.el_grid_resolution_deg is None:
            return np.array([0.0])
        return self._get_angles(
            self.num_el_angles(detection_volume),
            self.effective_el_angle_range(detection_volume),
        )

    def az_span(self, detection_volume: DetectionVolume) -> float:
        """Largest minus smallest az angle (0.0 when only one angle)."""
        a = self.az_angles(detection_volume)
        return float(a[-1] - a[0]) if len(a) > 1 else 0.0

    def n_el_interpolation(self, detection_volume: DetectionVolume) -> int:
        """Elevation interpolation half-width in cells. Falls back to 0 when
        fewer than ``2 * _N_EL_INTERPOLATION + 1`` el angles are configured."""
        return _N_EL_INTERPOLATION if self.num_el_angles(detection_volume) >= 3 else 0

    def get_cfar_radii(
        self,
        detection_volume: DetectionVolume,
        profile: a2.Profile,
        step_length_m: float,
        num_points: int,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """``(guard_radii, ref_radii)`` for the heatmap CFAR step.

        ``profile``, ``step_length_m``, and ``num_points`` come from the
        session config; ``detection_volume`` supplies the az grid
        (unless overridden by :py:attr:`az_angle_range`); the rest is taken
        from this config's CFAR fields.
        """
        return _compute_cfar_radii(
            az_span=self.az_span(detection_volume),
            num_az_angles=self.num_az_angles(detection_volume),
            profile=profile,
            step_length_m=step_length_m,
            num_points=num_points,
            az_guard_fwhm_factor=self.cfar_az_guard_fwhm_factor,
            dist_guard_envelope_len_factor=self.cfar_dist_guard_envelope_len_factor,
            az_reference_fwhm_factor=self.cfar_az_reference_fwhm_factor,
            dist_reference_envelope_len_factor=self.cfar_dist_reference_envelope_len_factor,
        )

    @property
    def cfar_theoretical_fpr(self) -> float:
        """CA-CFAR target false-positive rate derived from ``cfar_sensitivity`` (log-linear).

        ``cfar_sensitivity = 0`` -> FPR = ``_CFAR_FPR_MIN`` (strictest).
        ``cfar_sensitivity = 1`` -> FPR = ``_CFAR_FPR_MAX`` (loosest, no CFAR threshold).
        """
        return _sensitivity_to_fpr(self.cfar_sensitivity)

    def get_peak_finding_radii(
        self,
        detection_volume: DetectionVolume,
        profile: a2.Profile,
        step_length_m: float,
        num_points: int,
    ) -> tuple[int, int]:
        """``(n_dist, n_az)`` half-widths in cells used for both the 2D local-maxima
        search window and the 2D peak-interpolation fitting window. Elevation is
        handled separately via :py:meth:`n_el_interpolation`."""
        return _compute_peak_finding_radii(
            az_span=self.az_span(detection_volume),
            num_az_angles=self.num_az_angles(detection_volume),
            profile=profile,
            step_length_m=step_length_m,
            num_points=num_points,
            peak_finding_dist_radius_fwhm_factor=self.peak_finding_dist_radius_fwhm_factor,
            peak_finding_az_radius_fwhm_factor=self.peak_finding_az_radius_fwhm_factor,
        )

    def _collect_validation_results(
        self,
        session_config: a2.SessionConfig,
        sensor_installation: SensorInstallation,
        detection_volume: DetectionVolume,
    ) -> list[ValidationResult]:
        """Grid-aware validation: pair-range integrity, CFAR factor sanity,
        elevation-interpolation degradation, and peak-finding clamp
        warnings once translated through the actual session grid.

        The azimuth grid comes from ``detection_volume`` unless
        overridden by :py:attr:`az_angle_range`/:py:attr:`el_angle_range`; the
        distance grid comes from ``session_config``.
        """
        results: list[ValidationResult] = []

        # Pair-range integrity: ``lo < hi`` for every set ``(lo, hi)`` field.
        # The detection-volume offsets are deliberately absent: they are not
        # ranges but per-side offsets added to the detection volume's bounds,
        # so ``lo >= hi`` is meaningful there -- ``(0.0, 0.0)`` leaves the
        # volume unchanged and e.g. ``(0.5, -0.5)`` narrows it from both
        # sides. What must hold is that the *resulting* bound is non-empty,
        # which is checked against the actual volume further down.
        for name, bound in (
            ("az_angle_range", self.az_angle_range),
            ("el_angle_range", self.el_angle_range),
        ):
            if bound is None:
                continue
            lo, hi = bound
            if lo >= hi:
                results.append(
                    ValidationError(
                        self,
                        name,
                        f"{name}: lower bound {lo} must be smaller than upper bound {hi}.",
                    )
                )

        # Effective Cartesian bounds (detection volume offset by this
        # processor's override, if any) inside the sensor's physical reach.
        for name, offset, effective_bound in (
            (
                "detection_volume_x_bound_offset_m",
                self.detection_volume_x_bound_offset_m,
                self.effective_x_bounds_m(detection_volume),
            ),
            (
                "detection_volume_y_bound_offset_m",
                self.detection_volume_y_bound_offset_m,
                self.effective_y_bounds_m(detection_volume),
            ),
            (
                "detection_volume_z_bound_offset_m",
                self.detection_volume_z_bound_offset_m,
                self.effective_z_bounds_m(sensor_installation, detection_volume),
            ),
        ):
            if effective_bound is None:
                continue
            lo, hi = effective_bound
            # Non-empty resulting bound. This is the invariant the offsets
            # actually have to satisfy; it depends on the volume they are
            # applied to, so an offset pair cannot be judged on its own.
            if lo >= hi:
                results.append(
                    ValidationError(
                        self,
                        name,
                        f"{name}: offset {offset} applied to the detection "
                        f"volume leaves an empty bound ({lo}, {hi}); the "
                        f"offsets must leave lower < upper.",
                    )
                )
                continue
            if lo < -MAX_RANGE_M or hi > MAX_RANGE_M:
                results.append(
                    ValidationError(
                        self,
                        name,
                        f"{name}: effective bounds ({lo}, {hi}) must lie within "
                        f"[-{MAX_RANGE_M}, {MAX_RANGE_M}] — the processor "
                        f"does no translation, so detections cannot reach "
                        f"farther than _MAX_RANGE_M from the sensor.",
                    )
                )

        az_span = self.az_span(detection_volume)
        num_az_angles = self.num_az_angles(detection_volume)

        # CFAR az window vs az grid: the furthest reference cell sits at
        # ``(guard + reference)`` from the cut cell, so the half-span has to
        # accommodate that combined extent. ``_compute_cfar_radii`` clamps
        # each radius to ``(num_az_angles - 1) // 2`` independently, so a
        # combined extent above half the span is silently truncated.
        az_guard_radius_deg = self.cfar_az_guard_fwhm_factor * CONVENTIONAL_AZ_FWHM_DEG
        az_ref_radius_deg = self.cfar_az_reference_fwhm_factor * CONVENTIONAL_AZ_FWHM_DEG
        az_window_extent_deg = az_guard_radius_deg + az_ref_radius_deg
        if az_span > 0 and az_window_extent_deg > az_span / 2:
            results.append(
                ValidationWarning(
                    self,
                    "cfar_az_reference_fwhm_factor",
                    f"cfar guard + reference extent = "
                    f"{az_window_extent_deg:.2f} deg "
                    f"(guard {az_guard_radius_deg:.2f} deg + reference "
                    f"{az_ref_radius_deg:.2f} deg) exceeds half the az span "
                    f"({az_span:.2f} deg). The furthest reference cell "
                    f"falls outside the heatmap.",
                )
            )
        # Reference radius below half the az grid step rounds to 0 cells and
        # is floored to 1; the user's intent (a multi-cell reference window)
        # is lost.
        if num_az_angles > 1:
            az_step_deg = az_span / (num_az_angles - 1)
            if 0 < az_ref_radius_deg < az_step_deg / 2:
                results.append(
                    ValidationWarning(
                        self,
                        "cfar_az_reference_fwhm_factor",
                        f"cfar_az_reference_fwhm_factor = "
                        f"{self.cfar_az_reference_fwhm_factor} yields "
                        f"{az_ref_radius_deg:.2f} deg is below half the az "
                        f"grid step ({az_step_deg:.2f} deg); the reference window "
                        f"collapses to a single cell on each side.",
                    )
                )

        # Elevation interpolation requires >= 3 el angles. If the user
        # configured an el grid (resolution not None) but the resolution +
        # range yields too few angles, el interpolation is silently disabled.
        if self.el_grid_resolution_deg is not None and self.num_el_angles(detection_volume) < 3:
            results.append(
                ValidationWarning(
                    self,
                    "el_grid_resolution_deg",
                    f"el_grid_resolution_deg = {self.el_grid_resolution_deg} "
                    f"yields {self.num_el_angles(detection_volume)} el angles; "
                    f"elevation interpolation requires >= 3 angles and is "
                    f"disabled below that threshold.",
                )
            )

        # Subsweep consistency: the processor requires identical profile and step_length.
        subsweeps = session_config.sensor_config.subsweeps
        ref = subsweeps[0]
        consistent = True
        for i, subsweep in enumerate(subsweeps[1:], 1):
            if subsweep.profile != ref.profile:
                results.append(
                    ValidationError(
                        subsweep,
                        "profile",
                        f"All subsweeps must share the same profile; "
                        f"subsweep 0 has {ref.profile.name}, "
                        f"subsweep {i} has {subsweep.profile.name}.",
                    )
                )
                consistent = False
            if subsweep.step_length != ref.step_length:
                results.append(
                    ValidationError(
                        subsweep,
                        "step_length",
                        f"All subsweeps must share the same step_length; "
                        f"subsweep 0 has {ref.step_length}, "
                        f"subsweep {i} has {subsweep.step_length}.",
                    )
                )
                consistent = False

        if consistent:
            step_length_m = ref.step_length * BASE_STEP_LENGTH_M
            fwhm_m = ENVELOPE_FWHM_M[ref.profile]
            uncapped_n_dist = _cells_from_length(
                fwhm_m, step_length_m, self.peak_finding_dist_radius_fwhm_factor
            )
            if uncapped_n_dist > _MAX_PEAK_FINDING_DIST_RADIUS_BINS:
                results.append(
                    ValidationWarning(
                        self,
                        "peak_finding_dist_radius_fwhm_factor",
                        f"peak_finding_dist_radius_fwhm_factor = "
                        f"{self.peak_finding_dist_radius_fwhm_factor} would yield "
                        f"{uncapped_n_dist} distance bins on this grid; capped at "
                        f"{_MAX_PEAK_FINDING_DIST_RADIUS_BINS}.",
                    )
                )
            radius_deg = self.peak_finding_az_radius_fwhm_factor * CONVENTIONAL_AZ_FWHM_DEG
            uncapped_n_az = _cells_from_deg(az_span, num_az_angles, radius_deg)
            if uncapped_n_az > _MAX_PEAK_FINDING_AZ_RADIUS_BINS:
                results.append(
                    ValidationWarning(
                        self,
                        "peak_finding_az_radius_fwhm_factor",
                        f"peak_finding_az_radius_fwhm_factor = "
                        f"{self.peak_finding_az_radius_fwhm_factor} would yield "
                        f"{uncapped_n_az} azimuth bins on this grid; capped at "
                        f"{_MAX_PEAK_FINDING_AZ_RADIUS_BINS}.",
                    )
                )
        return results

    def validate(
        self,
        session_config: a2.SessionConfig,
        sensor_installation: SensorInstallation,
        detection_volume: DetectionVolume,
    ) -> None:
        """Run grid-aware validation against ``session_config`` and the
        geometry: raise ``ValidationError`` results, emit
        ``ValidationWarning`` results via the ``warnings`` system."""
        for validation_result in self._collect_validation_results(
            session_config, sensor_installation, detection_volume
        ):
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)


def get_walking_detection_configs() -> tuple[
    MotionDetectionConfig,
    WallMountSessionAbstractionConfig,
    SensorInstallation,
    DetectionVolume,
]:
    """5m detection config tuned for walking targets (no temporal high-pass)."""
    processor_config = MotionDetectionConfig(
        covariance_matrix_time_constant_s=0.15,
        high_pass_filter_time_constant_s=0.0,
        antenna_array=a2.AntennaArray.AP212,
        beamforming_method=BeamformingMethod.ROBUST_CAPON,
        spatial_high_pass_filter_time_constant_s=5.0,
        cfar_kernel_type=CFARKernelType.THICK_CROSS,
        cfar_aggregate_method=(CFARAggregateMethod.GO, CFARAggregateMethod.SO),
        cfar_az_guard_fwhm_factor=0.78,
        cfar_dist_guard_envelope_len_factor=0.5,
        cfar_az_reference_fwhm_factor=0.78,
        cfar_dist_reference_envelope_len_factor=0.5,
        cfar_sensitivity=0.75,
        peak_min_dist_separation_m=0.5,
        peak_interpolation_az_dist_method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT,
        az_grid_resolution_deg=2.0,
        el_grid_resolution_deg=15.0,
        detection_volume_x_bound_offset_m=(0.0, 0.0),
        detection_volume_y_bound_offset_m=(0.0, 0.0),
        detection_volume_z_bound_offset_m=None,
    )
    session_abstraction_config = WallMountSessionAbstractionConfig(
        signal_quality_db=22.0,
        profile=a2.Profile.PROFILE_7,
        max_snr_drop_db=2.5,
        sweeps_per_frame=8,
        sweep_rate=70.0,
        frame_rate=8.0,
    )
    sensor_installation = SensorInstallation(
        mount_height_m=2.0,
    )
    detection_volume = DetectionVolume(
        x_bounds_m=(-4.0, 4.0),
        y_bounds_m=(0.0, 6.0),
    )
    return processor_config, session_abstraction_config, sensor_installation, detection_volume


@attributes_doc
@attrs.mutable
class PlotSettings(AttrsMappingTransformsMixin):
    history_duration_s: float = attrs.field(default=2.0)
    """Duration of the scrolling peak-history window."""

    heatmap_display_mode: HeatmapDisplayMode = attrs.field(
        default=HeatmapDisplayMode.HEATMAP_MASKED,
        converter=HeatmapDisplayMode,
    )
    """Controls heatmap rendering: masked (below-threshold cells grey), full, or hidden."""


def get_sitting_detection_configs() -> tuple[
    MotionDetectionConfig,
    WallMountSessionAbstractionConfig,
    SensorInstallation,
    DetectionVolume,
]:
    """5m detection config tuned for sitting targets (0.5 s temporal high-pass)."""
    processor_config = MotionDetectionConfig(
        covariance_matrix_time_constant_s=0.15,
        high_pass_filter_time_constant_s=5.0,
        antenna_array=a2.AntennaArray.AP212,
        beamforming_method=BeamformingMethod.ROBUST_CAPON,
        spatial_high_pass_filter_time_constant_s=5.0,
        cfar_kernel_type=CFARKernelType.THICK_CROSS,
        cfar_aggregate_method=(CFARAggregateMethod.GO, CFARAggregateMethod.SO),
        cfar_az_guard_fwhm_factor=0.78,
        cfar_dist_guard_envelope_len_factor=0.5,
        cfar_az_reference_fwhm_factor=0.78,
        cfar_dist_reference_envelope_len_factor=0.5,
        cfar_sensitivity=0.75,
        peak_min_dist_separation_m=0.5,
        peak_interpolation_az_dist_method=InterpolationMethod2D.GAUSSIAN_INDEPENDENT,
        az_grid_resolution_deg=2.0,
        el_grid_resolution_deg=15.0,
        detection_volume_x_bound_offset_m=(0.0, 0.0),
        detection_volume_y_bound_offset_m=(0.0, 0.0),
        detection_volume_z_bound_offset_m=None,
    )
    session_abstraction_config = WallMountSessionAbstractionConfig(
        signal_quality_db=22.0,
        profile=a2.Profile.PROFILE_7,
        max_snr_drop_db=2.5,
        sweeps_per_frame=8,
        sweep_rate=70.0,
        frame_rate=8.0,
    )
    sensor_installation = SensorInstallation(
        mount_height_m=2.0,
    )
    detection_volume = DetectionVolume(
        x_bounds_m=(-4.0, 4.0),
        y_bounds_m=(0.0, 6.0),
    )
    return processor_config, session_abstraction_config, sensor_installation, detection_volume
