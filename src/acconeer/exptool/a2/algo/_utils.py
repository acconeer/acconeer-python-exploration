# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import copy
import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a2
from acconeer.exptool.a2._core.entities.configs.subsweep_config import UNSUPPORTED_TX_PRFS


BASE_STEP_LENGTH_M = 2.5e-3
HEATMAP_FALLBACK_UPDATE_RATE = 15.0


ENVELOPE_LENGTH_M: dict[a2.Profile, float] = {
    a2.Profile.PROFILE_1: 0.104,
    a2.Profile.PROFILE_2: 0.152,
    a2.Profile.PROFILE_3: 0.244,
    a2.Profile.PROFILE_4: 0.376,
    a2.Profile.PROFILE_5: 0.652,
    a2.Profile.PROFILE_6: 1.063,
    a2.Profile.PROFILE_7: 1.299,
}

MEAN_BASE_RLG_DB: dict[a2.Profile, float] = {
    a2.Profile.PROFILE_1: 21.63,
    a2.Profile.PROFILE_2: 22.38,
    a2.Profile.PROFILE_3: 24.00,
    a2.Profile.PROFILE_4: 24.78,
    a2.Profile.PROFILE_5: 25.00,
    a2.Profile.PROFILE_6: 27.02,
    a2.Profile.PROFILE_7: 27.90,
}

# Measured envelope full-width-at-half-maximum per profile (m).
# Values are the mean over temperature and channel.
ENVELOPE_FWHM_M: dict[a2.Profile, float] = {
    a2.Profile.PROFILE_1: 0.036,
    a2.Profile.PROFILE_2: 0.060,
    a2.Profile.PROFILE_3: 0.080,
    a2.Profile.PROFILE_4: 0.127,
    a2.Profile.PROFILE_5: 0.201,
    a2.Profile.PROFILE_6: 0.301,
    a2.Profile.PROFILE_7: 0.377,
}

# PRF → Maximum Measurable Distance (MMD) (m) mapping, ordered highest → lowest PRF (ascending MMD).
PRF_MMD_TABLE: dict[a2.PRF, float] = {
    a2.PRF.PRF_27_7_MHZ: 2.4,
    a2.PRF.PRF_20_8_MHZ: 4.2,
    a2.PRF.PRF_15_8_MHZ: 6.6,
    a2.PRF.PRF_12_5_MHZ: 9.0,
    a2.PRF.PRF_8_3_MHZ: 15.0,
    a2.PRF.PRF_5_3_MHZ: 25.0,
}

# Azimuth FWHM (degrees) of the conventional beamformer main lobe on the
# AP212 array. Profile-independent. Serves as an upper bound for Capon /
# robust-Capon variants where the lobe is narrower but FWHM is not a
# clean metric.
CONVENTIONAL_AZ_FWHM_DEG: float = 10.2

# JITTER_STD_DEG[profile][temperature_degC] = jitter std [deg]
# Profile 7: no 85 C measurement available; the 105 C value is reused as a stand-in.
JITTER_STD_DEG: dict[a2.Profile, dict[int, float]] = {
    a2.Profile.PROFILE_1: {-40: 1.92, 25: 1.86, 85: 1.97, 105: 2.06},
    a2.Profile.PROFILE_2: {-40: 1.92, 25: 1.92, 85: 2.05, 105: 2.11},
    a2.Profile.PROFILE_3: {-40: 1.97, 25: 2.00, 85: 2.13, 105: 2.18},
    a2.Profile.PROFILE_4: {-40: 2.06, 25: 2.11, 85: 2.29, 105: 2.30},
    a2.Profile.PROFILE_5: {-40: 2.24, 25: 2.30, 85: 2.53, 105: 2.58},
    a2.Profile.PROFILE_6: {-40: 2.41, 25: 2.36, 85: 2.57, 105: 2.58},
    a2.Profile.PROFILE_7: {-40: 2.56, 25: 2.41, 85: 2.57, 105: 2.57},
}


def estimate_max_update_rate(client: a2.Client, session_config: a2.SessionConfig) -> float:
    if client is None:
        raise RuntimeError
    if not client.connected:
        raise RuntimeError

    rate_config = copy.deepcopy(session_config)  # don't poke at the original session_config
    rate_config.update_rate = None

    n_samples = 12

    ticks: list[int] = []

    client.setup_session(rate_config)
    client.start_session()

    for i in range(n_samples):
        group_result = client.get_next(format=a2.Client.ResultFormat.FULL)
        ticks.append(group_result.results[0].tick)
    client.stop_session()

    mean_delta: float = np.mean(np.diff(ticks, n=1))
    max_update_rate: float = client.server_info.ticks_per_second / mean_delta

    return max_update_rate


def get_effective_frame_rate(
    session_config: a2.SessionConfig, sensor_config_ind: int = 0
) -> t.Optional[float]:
    """The rate frames arrive at: the sensor's ``frame_rate``, or the
    session's ``update_rate`` for sessions timed by the host. ``None`` if
    neither is set."""
    frame_rate = session_config.sensor_configs[sensor_config_ind].frame_rate
    if frame_rate is not None:
        return frame_rate
    return session_config.update_rate


def get_frame_phase(
    frame: npt.NDArray[np.complex128], *, degrees: bool = False
) -> npt.NDArray[np.float64]:
    """Gets the phase of a frame by averaging the argument (angle) across sweeps

    Examples:

    If the passed frame does not have exactly 2 dimensions, a ValueError is raised.

    >>> get_frame_phase(np.array([0.+0.j, 1.+0.j, 2.+0.j, 3.+0.j]))
    Traceback (most recent call last):
     ...
    ValueError: ...

    >>> get_frame_phase(np.array([[1.+1.j, 1.-1.j, -1.-1j, -1.+1j]]), degrees=True)
    array([ 45., -45., -135., 135.])

    >>> get_frame_phase(np.array([[1.+1.j, 1.-1.j],
    ...                           [-1.+1j, -1.-1j]]),
    ...                 degrees=True)
    array([ 90., -90.])
    """
    _assert_2d(frame)

    return np.mean(np.angle(frame, deg=degrees), axis=0)


def get_frame_envelope(frame: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
    """Gets the envelope of a frame but averaging the modulus (abs. value) across sweeps

    Examples:

    If the passed frame does not have exactly 2 dimensions, a ValueError is raised.

    >>> get_frame_envelope(np.array([0.+0.j, 1.+0.j, 2.+0.j, 3.+0.j]))
    Traceback (most recent call last):
     ...
    ValueError: ...

    >>> get_frame_envelope(np.array([[0.+0.j, 1.+0.j],
    ...                              [2.+0.j, 3.+0.j]]))
    array([1., 2.])
    """
    _assert_2d(frame)

    return np.mean(np.abs(frame), axis=0)


def get_points(start_point: int, step_length: int, num_points: int) -> npt.NDArray[np.int_]:
    """Get the points measured given the arguments

    Example:

    >>> get_points(start_point=0, step_length=4, num_points=5)
    array([ 0, 4, 8, 12, 16])
    """
    return np.fromiter(
        (start_point + i * step_length for i in range(num_points)),
        dtype=np.int_,
    )


def get_distances(
    start_point: int,
    step_length: int,
    num_points: int,
    base_step_length: float = BASE_STEP_LENGTH_M,
) -> npt.NDArray[np.float64]:
    """Get the distances specified by the arguments.

    Example:

    >>> get_distances(start_point=0, step_length=4, num_points=5)
    array([0.  , 0.01, 0.02, 0.03, 0.04])
    """
    points = get_points(start_point, step_length, num_points)
    return np.multiply(points, base_step_length, dtype=np.float64)


class _RssLikeRangeSpec(te.Protocol):
    """This is a protocol for object that specifies measured
    range in the same way as ``SubsweepConfig`` does.

    Exposed as properties (rather than plain instance annotations) so that
    read-only implementers like ``ConcatenatedSubsweepView`` structurally
    satisfy this protocol too, not just mutable ones like ``SubsweepConfig``.
    """

    @property
    def start_point(self) -> int: ...

    @property
    def step_length(self) -> int: ...

    @property
    def num_points(self) -> int: ...


def get_points_from_config(config: _RssLikeRangeSpec) -> npt.NDArray[np.int_]:
    """Get the points measured by the given config

    See :py:meth:`get_points`
    """
    return get_points(config.start_point, config.step_length, config.num_points)


def get_distances_from_config(
    config: _RssLikeRangeSpec,
    base_step_length: float = BASE_STEP_LENGTH_M,
) -> npt.NDArray[np.float64]:
    """Get the distances measured by the given config

    See :py:meth:`get_distances`
    """
    points = get_points_from_config(config)
    return np.multiply(points, base_step_length, dtype=np.float64)


def _to_subsweep_tuple(
    v: t.Sequence[a2.SubsweepConfig],
) -> tuple[a2.SubsweepConfig, ...]:
    # Deep-copy each config so the view is a true snapshot: the invariants
    # checked in __attrs_post_init__ stay valid even if the caller mutates
    # the SubsweepConfig objects they passed in afterwards.
    return tuple(copy.deepcopy(config) for config in v)


@attrs.frozen(kw_only=True)
class ConcatenatedSubsweepView:
    """Snapshot collapsing a run of contiguous, uniform ``SubsweepConfig``\\ s into one
    logical measurement range.

    All subsweeps must share ``tx_antenna_mask``, ``rx_antenna_mask``, ``profile``
    and ``step_length``, and must be contiguous: each subsweep must start exactly
    where the previous one ends (``next.start_point == prev.start_point +
    prev.num_points * prev.step_length``).
    """

    subsweep_configs: tuple[a2.SubsweepConfig, ...] = attrs.field(converter=_to_subsweep_tuple)

    def __attrs_post_init__(self) -> None:
        if not self.subsweep_configs:
            msg = "subsweep_configs must not be empty."
            raise ValueError(msg)
        self._validate_uniform("tx_antenna_mask")
        self._validate_uniform("rx_antenna_mask")
        self._validate_uniform("profile")
        self._validate_uniform("step_length")
        self._validate_contiguous_layout()

    def _validate_uniform(self, field_name: str) -> None:
        values = {getattr(config, field_name) for config in self.subsweep_configs}
        if len(values) != 1:
            msg = f"Expected the same {field_name} for all subsweeps, got {values}."
            raise ValueError(msg)

    def _validate_contiguous_layout(self) -> None:
        next_expected_start_point = self.subsweep_configs[0].start_point
        for i, config in enumerate(self.subsweep_configs):
            if config.start_point != next_expected_start_point:
                msg = (
                    f"Subsweep {i} starts at point {config.start_point} but the "
                    f"previous subsweep ends at point {next_expected_start_point}; "
                    f"subsweeps must be contiguous."
                )
                raise ValueError(msg)
            next_expected_start_point = config.start_point + config.num_points * config.step_length

    @classmethod
    def from_subsweeps(cls, subsweeps: t.Sequence[a2.SubsweepConfig]) -> ConcatenatedSubsweepView:
        return cls(subsweep_configs=subsweeps)

    @property
    def start_point(self) -> int:
        return self.subsweep_configs[0].start_point

    @property
    def step_length(self) -> int:
        (step_length,) = {config.step_length for config in self.subsweep_configs}
        return step_length

    @property
    def profile(self) -> a2.Profile:
        (profile,) = {config.profile for config in self.subsweep_configs}
        return profile

    @property
    def tx_antenna_mask(self) -> int:
        (mask,) = {config.tx_antenna_mask for config in self.subsweep_configs}
        return mask

    @property
    def rx_antenna_mask(self) -> int:
        (mask,) = {config.rx_antenna_mask for config in self.subsweep_configs}
        return mask

    @property
    def num_points(self) -> int:
        return sum(config.num_points for config in self.subsweep_configs)

    @property
    def num_channels(self) -> int:
        (num_channels,) = {config.num_channels for config in self.subsweep_configs}
        return num_channels


def get_measured_range(
    config: a2.SessionConfig, base_step_length: float = BASE_STEP_LENGTH_M
) -> tuple[float, float]:
    """Calculate the measured range (minimum point, maximum point) of a ``SessionConfig``.

    Examples:

    >>> config = a2.SessionConfig([a2.SensorConfig.single_subsweep(start_point=0,
    ...                                                            step_length=1,
    ...                                                            num_points=1),
    ...                            a2.SensorConfig.single_subsweep(start_point=120,
    ...                                                            step_length=1,
    ...                                                            num_points=80)],
    ...                           update_rate=None)
    >>> get_measured_range(config)
    (0.0, 0.4975)
    """
    subsweeps = [subsweep for sensor in config.sensor_configs for subsweep in sensor.subsweeps]
    return (
        min(ss.start_point for ss in subsweeps) * base_step_length,
        max(ss.end_point for ss in subsweeps) * base_step_length,
    )


def _assert_2d(frame: npt.NDArray[t.Any]) -> None:
    if frame.ndim != 2:
        msg = "A frame should always have 2 dimensions"
        raise ValueError(msg)


def db_to_lin(db: float) -> float:
    """Convert a dB value to linear power: ``10 ** (db / 10)``."""
    return float(10.0 ** (db / 10.0))


# Half-peak-length safety margin for choosing num_points (ensures no leakage):
# a measurement cannot start closer to the sensor than
# ``_PULSE_LENGTH_COMPENSATION_FACTOR * ENVELOPE_LENGTH_M / 2``.
_PULSE_LENGTH_COMPENSATION_FACTOR = 1.2


def get_max_step_length(profile: a2.Profile, max_snr_drop_db: float) -> int:
    """Max step length (in points) such that adjacent-sample envelope overlap
    keeps the power-domain SNR ripple within ``max_snr_drop_db``.

    Triangle-envelope model (rect * rect): amplitude is linear in distance
    from peak, ``amp(d) = 1 - d/L``, where L is the amplitude half-width.
    ``ENVELOPE_FWHM_M`` is the measured **power** (-3 dB) full width; for the
    triangle, ``FWHM_power = (1 - 1/sqrt(2)) * 2L``, so
    ``L = FWHM / (2 * (1 - 1/sqrt(2)))``.

    Two adjacent envelopes separated by ``step`` cross at amplitude
    ``1 - step/(2L)``. ``max_snr_drop_db`` is a power SNR drop at the
    crossing, so the amplitude there must be ``>= sqrt(1/dec_factor)``.
    Solving gives ``step <= 2L * (1 - sqrt(1/dec_factor))``, i.e.
    ``step <= FWHM * (1 - sqrt(1/dec_factor)) / (1 - 1/sqrt(2))``. At
    ``max_snr_drop_db = 3 dB`` (dec_factor = 2) this reduces to
    ``step = FWHM``, by definition of the half-power FWHM.
    """
    fwhm_m = ENVELOPE_FWHM_M[profile]
    dec_factor = db_to_lin(max_snr_drop_db)
    intersect = np.sqrt(1.0 / dec_factor)
    half_power_amp_drop = 1.0 - np.sqrt(0.5)  # ~= 0.293
    step_length_m = min(
        ENVELOPE_LENGTH_M[profile],
        max(BASE_STEP_LENGTH_M, fwhm_m * (1 - intersect) / half_power_amp_drop),
    )
    return int(np.round(step_length_m / BASE_STEP_LENGTH_M))


def get_point_grid_bounds(
    start_m: float, end_m: float, profile: a2.Profile, max_snr_drop_db: float
) -> t.Tuple[int, int]:
    """``(start_point, num_points)`` covering ``[start_m, end_m]`` at the step
    length ``get_max_step_length`` would choose for ``profile``/``max_snr_drop_db``.

    The session abstraction lays out its grid over a detection volume's range
    with this.
    """
    step_length = get_max_step_length(profile, max_snr_drop_db)
    # Closed form for the smallest n >= 1 such that the (n-th from the end)
    # sample's distance falls below threshold_m. Derived from
    # (end_m - threshold_m) >= step_length * B * (n + 0.5), where
    # B = BASE_STEP_LENGTH_M; n is bounded below by 1.
    pulse_length_m = ENVELOPE_LENGTH_M[profile] / 2
    half_peak_length_m = pulse_length_m * _PULSE_LENGTH_COMPENSATION_FACTOR
    threshold_m = max(half_peak_length_m, start_m)
    k = (end_m - threshold_m) / (step_length * BASE_STEP_LENGTH_M) - 0.5
    num_points = max(1, int(np.floor(k)) + 1)
    start_point = int(
        end_m / BASE_STEP_LENGTH_M - step_length / 2 - step_length * (num_points - 1)
    )
    return start_point, num_points


def get_prf_for_end_m(end_m: float, *, profile: a2.Profile) -> a2.PRF:
    """Highest PRF usable with ``profile`` (TX enabled) whose maximum
    measurable distance (MMD) covers ``end_m``.

    :raises ValueError: If no PRF usable with ``profile`` covers ``end_m``.
    """
    unsupported_prfs = UNSUPPORTED_TX_PRFS.get(profile, frozenset())
    for candidate_prf, mmd_m in PRF_MMD_TABLE.items():
        if mmd_m >= end_m and candidate_prf not in unsupported_prfs:
            return candidate_prf
    msg = f"No PRF covers end_m={end_m} m."
    raise ValueError(msg)


def hwaas_required(
    pos_m: t.Union[float, npt.NDArray[np.float64]],
    signal_quality_db: float,
    profile: a2.Profile,
    *,
    rlg_correction_db: t.Union[float, npt.NDArray[np.float64]] = 0.0,
    processing_gain_db: float = 0.0,
) -> t.Union[int, npt.NDArray[np.int_]]:
    """HWAAS per point needed to reach ``signal_quality_db`` at ``pos_m``.

    ``signal_quality_db`` is the approximate SNR for a 0 dBsm reflector, in
    dB. It is reached by solving this link budget for HWAAS::

        signal_quality_db = MEAN_BASE_RLG_DB[profile] + rlg_correction_db
                            + 10 * log10(HWAAS) - 40 * log10(pos_m)
                            + processing_gain_db

    The result is rounded up to an integer. The hardware cap is ignored;
    the caller is responsible for clamping to ``MAX_HWAAS``.

    Assumptions:

    * The target is a single point reflector with a radar cross section of
      0 dBsm, and the received power falls off as ``pos_m ** -4`` (free
      space, no multipath or occlusion).
    * ``MEAN_BASE_RLG_DB[profile]`` is the base RLG: the RLG of one channel
      and one sweep at HWAAS = 1. It is a mean over sensor individuals.
    * SNR grows by 10 * log10(HWAAS), i.e. 3 dB per doubling of HWAAS.
    * ``rlg_correction_db`` is an additive dB correction to the base RLG,
      e.g. from an angle-dependent antenna gain pattern. 0.0 means the
      target is on boresight.
    * ``processing_gain_db`` is every SNR gain beyond one channel and one
      sweep, provided by the caller, e.g. averaging sweeps, beamforming, and
      so on. Nothing is added implicitly.

    Accepts either scalars or numpy arrays for ``pos_m``/``rlg_correction_db``
    (returning a plain ``int`` or an ``int`` array to match), so it can be
    evaluated over a whole cloud of geometry samples at once.
    """
    pos_m_arr = np.asarray(pos_m, dtype=np.float64)
    if np.any(pos_m_arr <= 0.0):
        msg = "pos_m must be strictly positive (0 m or negative is not a valid range)"
        raise ValueError(msg)
    rlg_base_db = MEAN_BASE_RLG_DB[profile] + rlg_correction_db
    range_loss_db = 40.0 * np.log10(pos_m_arr)
    hwaas_needed_db = signal_quality_db + range_loss_db - rlg_base_db - processing_gain_db
    result = np.ceil(10.0 ** (hwaas_needed_db / 10.0)).astype(np.int_)
    return int(result) if result.ndim == 0 else result


def tc_to_sf(tc: float, fs: float) -> float:
    """Time constant to smoothing factor conversion.
    Assumed filter implementation is: y(k) = sf*y(k-1) + (1-sf)*x(k)
    """

    if tc <= 0.0:
        return 0.0

    return np.exp(-1.0 / (tc * fs))  # type: ignore[no-any-return]


def sf_to_tc(sf: float, fs: float) -> float:
    """Smoothing factor to time constant conversion"""

    if sf == 0.0 or sf == 1.0:
        return 0.0

    return -1 / (fs * np.log(sf))  # type: ignore[no-any-return]


def warmup_filter_const(beta: float, num_increments: int) -> float:
    return min(beta, num_increments / (num_increments + 1))
