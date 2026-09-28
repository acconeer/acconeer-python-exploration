# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import warnings

import attrs
import attrs.validators as av
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

import acconeer.exptool.type_migration as tm
from acconeer.exptool import a2
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from acconeer.exptool.a2._core.entities.configs.subsweep_config import (
    MAX_HWAAS,
    MAX_NUM_CHANNELS,
    MAX_RECEIVER_GAIN,
    MIN_RECEIVER_GAIN,
)
from acconeer.exptool.a2.algo import _rlg_correction as rlg_correction
from acconeer.exptool.a2.algo._detection_geometry import (
    CHEST_HEIGHT_M,
    DEFAULT_ROOM_HEIGHT_M,
    MAX_RANGE_M,
    DetectionVolume,
    SensorInstallation,
)
from acconeer.exptool.a2.algo._model_estimates import (
    estimated_max_frame_rate,
    estimated_max_sweep_rate,
)
from acconeer.exptool.a2.algo._subsweep_layout import solve_subsweep_layout
from acconeer.exptool.a2.algo._utils import (
    get_distances,
    get_max_step_length,
    get_point_grid_bounds,
    hwaas_required,
)
from acconeer.exptool.utils import cartesian_to_spherical, polar_to_cartesian


__all__ = [
    "MAX_RANGE_M",
    "WallMountSessionAbstractionConfig",
    "session_abstraction_config_timeline",
]

# Angle samples for _worst_case_rlg_correction_db. The coarse full-circle scan
# (1 degree) is finer than the ~2 degree grid of the RLG correction surface
# (_rlg_correction_grid.py). The fine scan spans +-1 coarse step around the
# coarse winner; its sample count must be odd so its middle sample is
# exactly the coarse winner.
_NUM_THETA_COARSE = 360
_NUM_THETA_FINE = 33


_NDf64 = npt.NDArray[np.float64]
_Bounds = tuple[float, float]
_UNBOUNDED: _Bounds = (-np.inf, np.inf)


def room_z_bounds_m(installation: SensorInstallation) -> tuple[float, float]:
    """World z bounds of the room: from the floor, ``installation.mount_height_m``
    below the sensor, up to ``DEFAULT_ROOM_HEIGHT_M`` above it."""
    floor_m = -installation.mount_height_m
    return floor_m, floor_m + DEFAULT_ROOM_HEIGHT_M


def _box_bounds(
    installation: SensorInstallation, volume: DetectionVolume
) -> tuple[_Bounds, _Bounds, _Bounds]:
    """The box's ``(lo, hi)`` per world axis, as high as ``installation``'s
    room (see :func:`room_z_bounds_m`); ``(-inf, inf)`` on every axis if the
    volume has no box."""
    if volume.x_bounds_m is None or volume.y_bounds_m is None:
        return _UNBOUNDED, _UNBOUNDED, _UNBOUNDED
    return volume.x_bounds_m, volume.y_bounds_m, room_z_bounds_m(installation)


def _required_range_m(
    installation: SensorInstallation, volume: DetectionVolume
) -> tuple[float, float]:
    """Range from the sensor to the nearest and farthest point of ``volume``,
    its box taken as high as ``installation``'s room (see :func:`room_z_bounds_m`).

    Each end is the stricter of the box's and ``start_m``/``end_m``.

    The box's ends are rotation-invariant: distance from the sensor does not
    depend on how it is oriented. Its farthest point is always at a corner:
    per axis, whichever bound has the larger magnitude maximizes the sum of
    squares. Its nearest point is not necessarily at a corner: per axis, if
    the sensor's own position (0) falls between that axis's bounds (as it
    always does without a box), the axis contributes nothing; only an axis
    lying entirely on one side of the sensor contributes the distance to its
    nearer bound. All three axes combine via the Euclidean norm, so the
    nearest point is 0 when the sensor is inside the box.

    :raises ValidationError: If ``volume`` does not validate, its farthest
        point exceeds the application's maximum range, or the box and
        ``start_m``/``end_m`` leave no range.
    """
    volume.validate()
    bounds = _box_bounds(installation, volume)
    near = [0.0 if lo <= 0.0 <= hi else min(abs(lo), abs(hi)) for lo, hi in bounds]
    far = [max(abs(lo), abs(hi)) for lo, hi in bounds]
    box_start_m = float(np.sqrt(sum(v * v for v in near)))
    box_end_m = float(np.sqrt(sum(v * v for v in far)))
    start_m = box_start_m if volume.start_m is None else max(volume.start_m, box_start_m)
    end_m = box_end_m if volume.end_m is None else min(volume.end_m, box_end_m)
    if end_m > MAX_RANGE_M:
        raise ValidationError(
            volume,
            "end_m",
            f"Farthest corner of the detection volume is {end_m:.2f} m from the sensor, "
            f"exceeding the application's maximum range of {MAX_RANGE_M:.1f} m. Shrink the "
            f"box or set end_m.",
        )
    if start_m >= end_m:
        # Blame the limit that empties the range: end_m short of the box, or
        # else start_m beyond it.
        short_end = volume.end_m is not None and volume.end_m <= box_start_m
        raise ValidationError(
            volume,
            "end_m" if short_end else "start_m",
            f"start_m/end_m leave no range inside the box, which spans "
            f"{box_start_m:.2f} to {box_end_m:.2f} m from the sensor.",
        )
    return start_m, end_m


def _in_volume(
    volume: DetectionVolume,
    points_world: _NDf64,
    az_deg: _NDf64,
    el_deg: _NDf64,
) -> npt.NDArray[np.bool_]:
    """``True`` where world points lie inside ``volume``, bounds included:
    in its box (in x and y), between ``start_m`` and ``end_m``, and within
    ``az_angle_range``/``el_angle_range``.

    :param points_world: World positions, along the last axis.
    :param az_deg: Sensor-frame azimuth of each point.
    :param el_deg: Sensor-frame elevation of each point.
    """
    inside = np.ones(points_world.shape[:-1], dtype=bool)
    for axis, bounds in enumerate((volume.x_bounds_m, volume.y_bounds_m)):
        if bounds is not None:
            lo, hi = bounds
            inside &= (points_world[..., axis] >= lo) & (points_world[..., axis] <= hi)
    if volume.start_m is not None or volume.end_m is not None:
        range_m = np.linalg.norm(points_world, axis=-1)
        if volume.start_m is not None:
            inside &= range_m >= volume.start_m
        if volume.end_m is not None:
            inside &= range_m <= volume.end_m
    az_lo, az_hi = volume.az_angle_range
    el_lo, el_hi = volume.el_angle_range
    inside &= (az_deg >= az_lo) & (az_deg <= az_hi) & (el_deg >= el_lo) & (el_deg <= el_hi)
    return inside


def _edge_crossing_xy(
    volume: DetectionVolume, rho_m: _NDf64
) -> tuple[_NDf64, _NDf64, npt.NDArray[np.bool_]]:
    """Points where circles centered on the sensor cross the edges of the
    box's x/y rectangle.

    Each circle has up to 8 crossings, 2 per edge. They are the endpoints
    of every arc of the circle inside the rectangle, however narrow. A
    volume without a box has no rectangle, and so no crossings.

    :param rho_m: Circle radii.
    :returns: ``(x_m, y_m, exists)``, each of shape ``(len(rho_m), 8)``.
        ``exists[i, k]`` is ``False`` where circle ``i`` does not reach
        that edge's line or crosses it outside the edge; ``x_m``/``y_m``
        there are finite but not a crossing.
    """
    num_r = len(rho_m)
    xs = np.zeros((num_r, 8))
    ys = np.zeros((num_r, 8))
    exists = np.zeros((num_r, 8), dtype=bool)
    if volume.x_bounds_m is None or volume.y_bounds_m is None:
        return xs, ys, exists
    x_lo, x_hi = volume.x_bounds_m
    y_lo, y_hi = volume.y_bounds_m

    def vertical_edge(col: int, c: float) -> None:
        half = np.sqrt(np.clip(rho_m**2 - c**2, 0.0, None))
        reaches = rho_m >= abs(c)
        for sign_idx, sign in enumerate((1.0, -1.0)):
            y_cand = sign * half
            xs[:, col + sign_idx] = c
            ys[:, col + sign_idx] = y_cand
            exists[:, col + sign_idx] = reaches & (y_cand >= y_lo) & (y_cand <= y_hi)

    def horizontal_edge(col: int, c: float) -> None:
        half = np.sqrt(np.clip(rho_m**2 - c**2, 0.0, None))
        reaches = rho_m >= abs(c)
        for sign_idx, sign in enumerate((1.0, -1.0)):
            x_cand = sign * half
            xs[:, col + sign_idx] = x_cand
            ys[:, col + sign_idx] = c
            exists[:, col + sign_idx] = reaches & (x_cand >= x_lo) & (x_cand <= x_hi)

    vertical_edge(0, x_lo)
    vertical_edge(2, x_hi)
    horizontal_edge(4, y_lo)
    horizontal_edge(6, y_hi)
    return xs, ys, exists


def _rlg_correction_db_at(
    installation: SensorInstallation,
    volume: DetectionVolume,
    x_m: _NDf64,
    y_m: _NDf64,
    z_m: float,
) -> tuple[_NDf64, npt.NDArray[np.bool_]]:
    """``rlg_correction_db`` at world points in the plane ``z = z_m``.

    :returns: ``(correction_db, observable)``. ``observable`` is ``True``
        where the point is inside the volume (see ``_in_volume``).
    """
    points_world = np.stack([x_m, y_m, np.full_like(x_m, z_m)], axis=-1)
    points_sensor = installation.world_to_sensor(points_world)
    _, az_rad, el_rad = cartesian_to_spherical(
        points_sensor[..., 0], points_sensor[..., 1], points_sensor[..., 2]
    )
    az_deg, el_deg = np.degrees(az_rad), np.degrees(el_rad)
    observable = _in_volume(volume, points_world, az_deg, el_deg)
    return rlg_correction.rlg_correction_db(az_deg, el_deg), observable


def _worst_case_rlg_correction_db(
    installation: SensorInstallation,
    volume: DetectionVolume,
    distances_m: _NDf64,
    z_eval_m: float,
) -> tuple[_NDf64, npt.NDArray[np.bool_]]:
    """Most negative ``rlg_correction_db`` per ``distances_m`` point, over the
    observable points at that range on the plane ``z = z_eval_m``: inside
    the volume (see ``_in_volume``).

    Takes the worst of two searches:

    * A coarse full-circle scan, refined by a fine scan around its worst
      sample. Finds interior minima of the correction surface.
    * The box-edge crossings (``_edge_crossing_xy``), i.e. the endpoints of
      every in-box arc. Needed because the in-box arc narrows to zero width
      near a box corner, and the farthest ``distances_m`` points lie close
      to the corner distance (``_required_range_m``), where the scan may
      find no sample.

    :returns: ``(worst_correction_db, row_has_any)``. ``row_has_any[i]`` is
        ``False`` where no observable point exists at ``distances_m[i]``:
        below the plane's reachable minimum, or outside the volume.
        ``worst_correction_db`` is ``+inf`` there.
    """
    plane_radius_sq = distances_m**2 - z_eval_m**2
    feasible_r = plane_radius_sq >= 0.0
    plane_radius_m = np.sqrt(np.clip(plane_radius_sq, 0.0, None))  # (num_r,)

    # Coarse full-circle scan, for every distances_m point at once.
    theta_coarse = np.linspace(0.0, 2.0 * np.pi, _NUM_THETA_COARSE, endpoint=False)
    correction_c, observable_c = _rlg_correction_db_at(
        installation,
        volume,
        *polar_to_cartesian(plane_radius_m[:, None], theta_coarse[None, :]),
        z_eval_m,
    )
    valid_c = observable_c & feasible_r[:, None]
    correction_c_masked = np.where(valid_c, correction_c, np.inf)
    row_has_any = np.any(valid_c, axis=1)
    theta0 = theta_coarse[np.argmin(correction_c_masked, axis=1)]  # (num_r,)

    # Fine scan over +-1 coarse step around theta0. Its middle sample is
    # theta0 itself, so it never does worse than the coarse scan.
    coarse_step = 2.0 * np.pi / _NUM_THETA_COARSE
    offsets = np.linspace(-coarse_step, coarse_step, _NUM_THETA_FINE)
    theta_fine = theta0[:, None] + offsets[None, :]
    correction_f, observable_f = _rlg_correction_db_at(
        installation,
        volume,
        *polar_to_cartesian(plane_radius_m[:, None], theta_fine),
        z_eval_m,
    )
    valid_f = observable_f & feasible_r[:, None]
    correction_f_masked = np.where(valid_f, correction_f, np.inf)

    # Box-edge crossings: the endpoints of every in-box arc, however narrow.
    x_edge, y_edge, exists_edge = _edge_crossing_xy(volume, plane_radius_m)
    correction_e, observable_e = _rlg_correction_db_at(
        installation, volume, x_edge, y_edge, z_eval_m
    )
    valid_e = observable_e & exists_edge & feasible_r[:, None]
    correction_e_masked = np.where(valid_e, correction_e, np.inf)

    row_has_any = row_has_any | np.any(valid_e, axis=1)
    worst_correction_db = np.minimum(
        np.min(correction_f_masked, axis=1), np.min(correction_e_masked, axis=1)
    )
    return worst_correction_db, row_has_any


def _fill_empty_bins_by_log_interp(required: npt.NDArray[np.float64]) -> None:
    """Replace the ``-inf`` entries of ``required``, in place, by linear
    interpolation in log space between the nearest finite entries, rounded
    up. Entries before the first or after the last finite entry take that
    entry's value.

    :param required: Required HWAAS per point, ``-inf`` where empty. Must
        have at least one finite entry.
    """
    is_empty = np.isneginf(required)
    if not np.any(is_empty):
        return
    filled_idx = np.flatnonzero(~is_empty)
    log_required = np.log(required[filled_idx])
    all_idx = np.arange(len(required))
    interpolated_log = np.interp(all_idx, filled_idx, log_required)
    required[is_empty] = np.exp(interpolated_log[is_empty])
    required[is_empty] = np.ceil(required[is_empty])


@attributes_doc
@attrs.mutable
class WallMountSessionAbstractionConfig(AttrsMappingTransformsMixin):
    signal_quality_db: float = attrs.field(validator=av.gt(0.0))
    """Signal quality (SNR in dB) for a 0 dBsm reflector, guaranteed at every
    point of the ``snr_evaluation_height_m`` plane inside the paired
    ``DetectionVolume`` (see :meth:`get_session_config`).

    Includes the processing gain from using all 12 TX/RX channels and all
    sweeps within a frame."""

    profile: a2.Profile = attrs.field(converter=a2.Profile)
    """The profile used."""

    frame_rate: float = attrs.field(validator=av.gt(0.0))
    """Frame rate used (Hz). The sensor times the frames itself."""

    max_snr_drop_db: float = attrs.field(default=1.0, validator=[av.ge(0.0), av.le(3.0)])
    """Maximum SNR drop (power-domain dB) allowed between adjacent sample
    points; sets the step length. At most 3 dB. A lower value gives more
    points."""

    sweeps_per_frame: int = attrs.field(default=8, validator=av.gt(0))
    """The number of sweeps used per frame."""

    sweep_rate: float | None = attrs.field(kw_only=True)
    """Sweep rate used (Hz). ``None`` lets the sensor pick the maximum allowed
    given the configured profile, HWAAS and step length."""

    receiver_gain: int = attrs.field(
        default=5, validator=[av.ge(MIN_RECEIVER_GAIN), av.le(MAX_RECEIVER_GAIN)]
    )
    """Receiver gain."""

    max_num_subsweeps: int = attrs.field(
        default=a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1,
        validator=[av.ge(1), av.le(a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1)],
    )
    """Upper bound on how many subsweeps :meth:`get_session_config` may use.

    At most ``MAX_NUM_SUBSWEEPS - 1``: ``_make_sensor_config`` always enables
    ``jitter_compensation``, which occupies one subsweep slot (see
    ``SensorConfig`` validation)."""

    snr_evaluation_height_m: float = attrs.field(
        default=CHEST_HEIGHT_M,
        kw_only=True,
        validator=[av.ge(0.0), av.le(DEFAULT_ROOM_HEIGHT_M)],
    )
    """Height above the floor, in meters, at which signal_quality_db is
    evaluated and guaranteed. The default, 1.2 m, is about the chest height of
    persons in front of the sensor. At most 2.5 m, the room's height.
    Must not lie below the floor,
    ``mount_height_m`` below the sensor; ``get_session_config`` raises
    ``ValidationError`` otherwise."""

    def _snr_evaluation_z_m(self, sensor_installation: SensorInstallation) -> float:
        """World z of the ``snr_evaluation_height_m`` plane; the floor is
        ``mount_height_m`` below the sensor."""
        return self.snr_evaluation_height_m - sensor_installation.mount_height_m

    def _collect_validation_results(
        self, sensor_installation: SensorInstallation, detection_volume: DetectionVolume
    ) -> list[ValidationResult]:
        validation_results: list[ValidationResult] = []
        try:
            session_config = self.get_session_config(sensor_installation, detection_volume)
        except ValidationError as error:
            # An invalid or out-of-range volume, or an evaluation plane
            # below the floor or with no observable point:
            # either way there is no session config to check further.
            validation_results.append(error)
            return validation_results

        validation_results.extend(
            self._rate_feasibility_checks(session_config, sensor_installation, detection_volume)
        )
        return validation_results

    def _rate_feasibility_checks(
        self,
        session_config: a2.SessionConfig,
        sensor_installation: SensorInstallation,
        detection_volume: DetectionVolume,
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        sweep_rate_too_low = False

        max_frame_rate = estimated_max_frame_rate(session_config)
        if self.frame_rate > max_frame_rate:
            # A frame that would fit at the maximum sweep rate is out of reach
            # only because of the set sweep_rate, which signal quality and the
            # volume cannot fix.
            if self.sweep_rate is not None:
                at_max_sweep_rate = attrs.evolve(self, sweep_rate=None).get_session_config(
                    sensor_installation, detection_volume
                )
                sweep_rate_too_low = self.frame_rate <= estimated_max_frame_rate(at_max_sweep_rate)
            if sweep_rate_too_low:
                message = (
                    "Sweep rate too low for the frame rate. "
                    "Increase the sweep rate or decrease the frame rate."
                )
                results.append(ValidationError(self, "frame_rate", message))
                results.append(ValidationError(self, "sweep_rate", message))
            else:
                results.append(
                    ValidationError(
                        self,
                        "frame_rate",
                        f"frame_rate ({self.frame_rate:.2f} Hz) exceeds the maximum "
                        f"frame rate ({max_frame_rate:.2f} Hz) for this configuration. "
                        f"Reduce frame_rate, or decrease signal_quality_db, or shrink the volume.",
                    )
                )

        if self.sweep_rate is not None:
            max_sweep_rate = estimated_max_sweep_rate(session_config.sensor_config)
            if self.sweep_rate > max_sweep_rate:
                results.append(
                    ValidationError(
                        self,
                        "sweep_rate",
                        f"sweep_rate ({self.sweep_rate:.2f} Hz) exceeds the maximum "
                        f"sweep rate ({max_sweep_rate:.2f} Hz) for this configuration. "
                        f"Reduce sweep_rate (or set to None for auto), decrease "
                        f"signal_quality_db or shrink the volume.",
                    )
                )

        # The rate fields are advanced settings, so an infeasible
        # configuration, or one whose HWAAS is capped at the hardware limit,
        # is also pointed at the settings users actually change.
        hwaas_saturates = any(
            subsweep.hwaas_max >= MAX_HWAAS for subsweep in session_config.sensor_config.subsweeps
        )
        if (results and not sweep_rate_too_low) or hwaas_saturates:
            results = [
                ValidationWarning(
                    self,
                    "signal_quality_db",
                    "Signal quality too high for the set detection volume. "
                    "Decrease signal quality.",
                ),
                ValidationWarning(
                    detection_volume,
                    # Without a box, end_m is what sizes the volume.
                    "y_bounds_m" if detection_volume.y_bounds_m is not None else "end_m",
                    "Detection volume too large for the set signal quality. "
                    "Shrink the detection volume.",
                ),
                *results,
            ]

        return results

    def _check_snr_evaluation_height_above_floor(
        self, sensor_installation: SensorInstallation
    ) -> None:
        """:raises ValidationError: If the ``snr_evaluation_height_m`` plane
        lies below the floor, ``mount_height_m`` below the sensor."""
        floor_z_m = -sensor_installation.mount_height_m
        if self._snr_evaluation_z_m(sensor_installation) < floor_z_m:
            raise ValidationError(
                self,
                "snr_evaluation_height_m",
                f"snr_evaluation_height_m ({self.snr_evaluation_height_m:.2f} m) lies below "
                f"the floor, {sensor_installation.mount_height_m:.2f} m below the sensor.",
            )

    def validate(
        self, sensor_installation: SensorInstallation, detection_volume: DetectionVolume
    ) -> None:
        """Run cross-field validation: raise the first ``ValidationError``,
        emit ``ValidationWarning`` results via the ``warnings`` system."""
        for validation_result in self._collect_validation_results(
            sensor_installation, detection_volume
        ):
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)

    def _get_point_grid_bounds(
        self, sensor_installation: SensorInstallation, detection_volume: DetectionVolume
    ) -> tuple[int, int]:
        """``(start_point, num_points)`` of the grid covering the volume's
        range (see ``_required_range_m``)."""
        start_m, end_m = _required_range_m(sensor_installation, detection_volume)
        return get_point_grid_bounds(start_m, end_m, self.profile, self.max_snr_drop_db)

    def _get_max_step_length(self) -> int:
        return get_max_step_length(self.profile, self.max_snr_drop_db)

    def _sweep_averaging_gain_db(self) -> float:
        """SNR gain (dB) from averaging across sweeps, as seen on the heatmap.

        Theoretical, not measured. Both schemes reduce the variance of their
        averaged quantity by ``1/N`` (just sample-mean variance) — the
        difference is what the beamformer measures on the result:

        * Coherent sweep averaging (``x_avg = mean(x_k)``) followed by
          beamforming: the heatmap is exponentially distributed with mean
          ``sigma^2 |a|^2 / N``. The noise floor itself moves down by ``1/N``
          → SNR gain ``10·log10(N)`` dB.

        * Covariance-matrix averaging (the motion-detection processor):
          ``h = a^H C_avg a = (1/N) sum |a^H x_k|^2 ~ Gamma(N, sigma^2 |a|^2 / N)``.
          The heatmap *mean* stays at ``sigma^2 |a|^2`` — the noise floor does
          not move. Only the fluctuations around it shrink: the coefficient of
          variation drops as ``1/sqrt(N)``. For detection, that ``sqrt(N)``
          improvement in noise-floor stability is the effective gain
          → ``5·log10(N)`` dB.
        """
        return float(5.0 * np.log10(self.sweeps_per_frame))

    def _channel_gain_db(self) -> float:
        """SNR gain (dB) from coherently combining the channels in the
        beamformer: ``10·log10(num_channels)``. Assumes that all available TX/RX
        channels are used (num_channels = MAX_NUM_CHANNELS)."""
        return float(10.0 * np.log10(MAX_NUM_CHANNELS))

    def _processing_gain_db(self) -> float:
        """Total SNR gain beyond one channel and one sweep, as
        ``hwaas_required`` expects it: channel combination plus sweep
        averaging."""
        return self._channel_gain_db() + self._sweep_averaging_gain_db()

    def _make_sensor_config(self, subsweeps: list[a2.SubsweepConfig]) -> a2.SensorConfig:
        return a2.SensorConfig(
            subsweeps=subsweeps,
            sweeps_per_frame=self.sweeps_per_frame,
            jitter_compensation=True,
            sweep_rate=self.sweep_rate,
            frame_rate=self.frame_rate,
            inter_frame_idle_state=a2.IdleState.ARMED,
            inter_sweep_idle_state=a2.IdleState.ARMED,
        )

    def _required_hwaas_curve(
        self,
        sensor_installation: SensorInstallation,
        detection_volume: DetectionVolume,
        distances_m: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        """HWAAS required for ``signal_quality_db`` at every point in
        ``distances_m``, at the worst observable point at that range.

        At fixed range, the only angle-dependent term of ``hwaas_required`` is
        ``rlg_correction_db``, so the worst point is the one minimizing it
        (see ``_worst_case_rlg_correction_db``). Observable points lie on the
        ``snr_evaluation_height_m`` plane, inside the volume; the processors'
        beamforming grid (e.g. ``PresenceTrackingConfig.az_angles``) covers
        only its ``az_angle_range``. Ranges with no observable point are
        filled from their neighbors (see ``_fill_empty_bins_by_log_interp``).

        :raises ValidationError: If no range has an observable point.
        """
        worst_correction_db, row_has_any = _worst_case_rlg_correction_db(
            sensor_installation,
            detection_volume,
            distances_m,
            self._snr_evaluation_z_m(sensor_installation),
        )
        if not np.any(row_has_any):
            raise ValidationError(
                self,
                "snr_evaluation_height_m",
                "No point on the snr_evaluation_height_m plane "
                f"({self.snr_evaluation_height_m:.2f} m above the floor) is both inside the "
                "detection volume and within its az_angle_range/el_angle_range, so the SNR "
                "guarantee cannot be evaluated. Move snr_evaluation_height_m, widen the angle "
                "ranges, or change the mount rotation.",
            )
        needed = hwaas_required(
            distances_m,
            self.signal_quality_db,
            self.profile,
            rlg_correction_db=worst_correction_db,
            processing_gain_db=self._processing_gain_db(),
        )
        # hwaas_required returns an array here since distances_m is one; the ``int``
        # branch of its Union return only applies to scalar input.
        required = np.where(row_has_any, needed.astype(float), -np.inf)  # type: ignore[union-attr]
        _fill_empty_bins_by_log_interp(required)
        return required

    def get_session_config(
        self, sensor_installation: SensorInstallation, detection_volume: DetectionVolume
    ) -> a2.SessionConfig:
        """Build the runtime session config from tuning settings and the
        supplied geometry: a <=``max_num_subsweeps``, angle-aware,
        dynamic-HWAAS layout guaranteeing ``signal_quality_db`` at the
        ``snr_evaluation_height_m`` plane inside ``detection_volume`` as seen from
        ``sensor_installation``, minimizing estimated power
        (see :func:`~acconeer.exptool.a2.algo._subsweep_layout.solve_subsweep_layout`).

        :raises ValidationError: If the volume does not validate or exceeds
            the application's maximum range, ``snr_evaluation_height_m`` lies below
            the floor, or the plane has no observable point.
        """
        start_point, num_points = self._get_point_grid_bounds(
            sensor_installation, detection_volume
        )
        self._check_snr_evaluation_height_above_floor(sensor_installation)
        step_length = self._get_max_step_length()
        distances_m = get_distances(start_point, step_length, num_points)

        required = self._required_hwaas_curve(sensor_installation, detection_volume, distances_m)
        subsweeps = solve_subsweep_layout(
            required,
            start_point=start_point,
            profile=self.profile,
            step_length=step_length,
            receiver_gain=self.receiver_gain,
            max_num_subsweeps=self.max_num_subsweeps,
        )
        sensor_config = self._make_sensor_config(subsweeps)
        return a2.SessionConfig([sensor_config], update_rate=None)

    def try_get_session_config(
        self, sensor_installation: SensorInstallation, detection_volume: DetectionVolume
    ) -> a2.SessionConfig | None:
        """``get_session_config``, or ``None`` if it raises ``ValidationError``

        Validation reports why.
        """
        try:
            return self.get_session_config(sensor_installation, detection_volume)
        except ValidationError:
            return None


@attrs.mutable
class _WallMountSessionAbstractionConfig_v0(AttrsMappingTransformsMixin):
    signal_quality_break_point_m: float = attrs.field(validator=[av.ge(0.0), av.le(MAX_RANGE_M)])
    profile: a2.Profile = attrs.field(converter=a2.Profile)
    update_rate: float = attrs.field(validator=av.gt(0.0))
    max_snr_drop_db: float = attrs.field(default=1.0, validator=[av.ge(0.0), av.le(3.0)])
    signal_quality_close_db: float = attrs.field(default=20.5, validator=av.gt(0.0))
    signal_quality_far_db: float = attrs.field(default=20.5, validator=av.gt(0.0))
    hwaas_min: int = attrs.field(default=3, validator=av.gt(0))
    sweeps_per_frame: int = attrs.field(default=8, validator=av.gt(0))
    sweep_rate: float | None = attrs.field(default=None)
    receiver_gain: int = attrs.field(
        default=5, validator=[av.ge(MIN_RECEIVER_GAIN), av.le(MAX_RECEIVER_GAIN)]
    )

    def migrate(self) -> _WallMountSessionAbstractionConfig_v1:
        # signal_quality_db is the lower of the two old targets, so it never
        # overstates what the recording guaranteed. signal_quality_break_point_m
        # and hwaas_min are dropped. snr_evaluation_z_m is set to sensor height
        # and max_num_subsweeps to its maximum.
        return _WallMountSessionAbstractionConfig_v1(
            signal_quality_db=min(self.signal_quality_close_db, self.signal_quality_far_db),
            profile=self.profile,
            update_rate=self.update_rate,
            max_snr_drop_db=self.max_snr_drop_db,
            sweeps_per_frame=self.sweeps_per_frame,
            sweep_rate=self.sweep_rate,
            receiver_gain=self.receiver_gain,
            snr_evaluation_z_m=0.0,
            max_num_subsweeps=a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1,
        )


@attrs.mutable
class _WallMountSessionAbstractionConfig_v1(AttrsMappingTransformsMixin):
    signal_quality_db: float = attrs.field(validator=av.gt(0.0))
    profile: a2.Profile = attrs.field(converter=a2.Profile)
    update_rate: float = attrs.field(validator=av.gt(0.0))
    max_snr_drop_db: float = attrs.field(default=1.0, validator=[av.ge(0.0), av.le(3.0)])
    sweeps_per_frame: int = attrs.field(default=8, validator=av.gt(0))
    sweep_rate: float | None = attrs.field(kw_only=True)
    receiver_gain: int = attrs.field(
        default=5, validator=[av.ge(MIN_RECEIVER_GAIN), av.le(MAX_RECEIVER_GAIN)]
    )
    max_num_subsweeps: int = attrs.field(
        default=a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1,
        validator=[av.ge(1), av.le(a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1)],
    )
    snr_evaluation_z_m: float = attrs.field(
        kw_only=True, validator=[av.ge(-MAX_RANGE_M), av.le(MAX_RANGE_M)]
    )

    def migrate(self) -> _WallMountSessionAbstractionConfig_v2:
        # The session was timed by SessionConfig.update_rate; the sensor now
        # times the frames at the same rate.
        return _WallMountSessionAbstractionConfig_v2(
            signal_quality_db=self.signal_quality_db,
            profile=self.profile,
            frame_rate=self.update_rate,
            max_snr_drop_db=self.max_snr_drop_db,
            sweeps_per_frame=self.sweeps_per_frame,
            sweep_rate=self.sweep_rate,
            receiver_gain=self.receiver_gain,
            max_num_subsweeps=self.max_num_subsweeps,
            snr_evaluation_z_m=self.snr_evaluation_z_m,
        )


@attrs.mutable
class _WallMountSessionAbstractionConfig_v2(AttrsMappingTransformsMixin):
    signal_quality_db: float = attrs.field(validator=av.gt(0.0))
    profile: a2.Profile = attrs.field(converter=a2.Profile)
    frame_rate: float = attrs.field(validator=av.gt(0.0))
    max_snr_drop_db: float = attrs.field(default=1.0, validator=[av.ge(0.0), av.le(3.0)])
    sweeps_per_frame: int = attrs.field(default=8, validator=av.gt(0))
    sweep_rate: float | None = attrs.field(kw_only=True)
    receiver_gain: int = attrs.field(
        default=5, validator=[av.ge(MIN_RECEIVER_GAIN), av.le(MAX_RECEIVER_GAIN)]
    )
    max_num_subsweeps: int = attrs.field(
        default=a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1,
        validator=[av.ge(1), av.le(a2.SensorConfig.MAX_NUM_SUBSWEEPS - 1)],
    )
    snr_evaluation_z_m: float = attrs.field(
        kw_only=True, validator=[av.ge(-MAX_RANGE_M), av.le(MAX_RANGE_M)]
    )

    def migrate(
        self, completer: tm.Completer[SensorInstallation]
    ) -> WallMountSessionAbstractionConfig:
        # snr_evaluation_z_m was relative to the sensor, so it becomes a height
        # above the floor of the installation the completer gives: the one
        # recorded alongside this config.
        mount_height_m = completer(SensorInstallation).mount_height_m
        return WallMountSessionAbstractionConfig(
            signal_quality_db=self.signal_quality_db,
            profile=self.profile,
            frame_rate=self.frame_rate,
            max_snr_drop_db=self.max_snr_drop_db,
            sweeps_per_frame=self.sweeps_per_frame,
            sweep_rate=self.sweep_rate,
            receiver_gain=self.receiver_gain,
            max_num_subsweeps=self.max_num_subsweeps,
            snr_evaluation_height_m=self.snr_evaluation_z_m + mount_height_m,
        )


session_abstraction_config_timeline = (
    tm.start(_WallMountSessionAbstractionConfig_v0)
    .load(dict, _WallMountSessionAbstractionConfig_v0.from_dict, fail=[TypeError])
    .load(
        str, _WallMountSessionAbstractionConfig_v0.from_json, fail=tm.common_exceptions.FROM_JSON
    )
    .epoch(
        _WallMountSessionAbstractionConfig_v1,
        _WallMountSessionAbstractionConfig_v0.migrate,
        fail=[],
    )
    .load(dict, _WallMountSessionAbstractionConfig_v1.from_dict, fail=[TypeError])
    .load(
        str, _WallMountSessionAbstractionConfig_v1.from_json, fail=tm.common_exceptions.FROM_JSON
    )
    .epoch(
        _WallMountSessionAbstractionConfig_v2,
        _WallMountSessionAbstractionConfig_v1.migrate,
        fail=[],
    )
    .load(dict, _WallMountSessionAbstractionConfig_v2.from_dict, fail=[TypeError])
    .load(
        str, _WallMountSessionAbstractionConfig_v2.from_json, fail=tm.common_exceptions.FROM_JSON
    )
    .contextual_epoch(
        WallMountSessionAbstractionConfig,
        _WallMountSessionAbstractionConfig_v2.migrate,
        fail=[],
    )
    .load(dict, WallMountSessionAbstractionConfig.from_dict, fail=[TypeError])
    .load(str, WallMountSessionAbstractionConfig.from_json, fail=tm.common_exceptions.FROM_JSON)
)
