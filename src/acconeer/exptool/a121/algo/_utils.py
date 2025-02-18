# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import copy
import enum
from typing import Any, Optional, Tuple, Union

import numpy as np
import numpy.typing as npt
from scipy.signal import butter, filtfilt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoParamEnum


ENVELOPE_FWHM_M = {
    a121.Profile.PROFILE_1: 0.04,
    a121.Profile.PROFILE_2: 0.07,
    a121.Profile.PROFILE_3: 0.14,
    a121.Profile.PROFILE_4: 0.19,
    a121.Profile.PROFILE_5: 0.32,
}
APPROX_BASE_STEP_LENGTH_M = 2.5e-3
# Parameter of signal temperature model.
SIGNAL_TEMPERATURE_MODEL_PARAMETER = {
    a121.Profile.PROFILE_1: 67.0,
    a121.Profile.PROFILE_2: 85.0,
    a121.Profile.PROFILE_3: 86.0,
    a121.Profile.PROFILE_4: 99.0,
    a121.Profile.PROFILE_5: 104.0,
}
# Largest measurable distance per PRF.
MAX_MEASURABLE_DIST_M = {prf: prf.mmd for prf in set(a121.PRF)}
# Slope and interception of linear noise temperature model.
DEVIATION_TEMPERATURE_MODEL_PARAMETER = [-0.00275, 0.98536]

SPEED_OF_LIGHT = 299792458
RADIO_FREQUENCY = 60.5e9
WAVELENGTH = SPEED_OF_LIGHT / RADIO_FREQUENCY
PERCEIVED_WAVELENGTH = WAVELENGTH / 2

MEAN_ABS_DEV_OUTLIER_TH = 5

RLG_PER_HWAAS_MAP = {
    a121.Profile.PROFILE_1: 11.3,
    a121.Profile.PROFILE_2: 13.7,
    a121.Profile.PROFILE_3: 19.0,
    a121.Profile.PROFILE_4: 20.5,
    a121.Profile.PROFILE_5: 21.6,
}

SPARSE_IQ_PPC = 24


class ReflectorShape(AlgoParamEnum):
    """Reflector shape.

    ``GENERIC`` Reflectors of any shape.
    ``PLANAR`` Planar shaped reflectors facing the radar, for example water surfaces.
    """

    GENERIC = 4
    PLANAR = 2

    @property
    def exponent(self) -> float:
        return float(self.value)


class PeakSortingMethod(AlgoParamEnum):
    """Peak sorting methods.
    ``CLOSEST`` sort according to distance.
    ``STRONGEST`` sort according to strongest reflector."""

    CLOSEST = enum.auto()
    STRONGEST = enum.auto()


def get_distance_offset(
    peak_location: Optional[float], profile: a121.Profile, temperature: Optional[Union[float, int]]
) -> float:
    """
    Returns the distance offset in meters based on a loopback measurement.
    """
    if peak_location is None:
        return 0.0

    if temperature is not None:
        if temperature < -25:
            OFFSET_COMPENSATION_COEFFS = {
                a121.Profile.PROFILE_1: [0.81796372, 0.01561084],
                a121.Profile.PROFILE_2: [0.60363902, 0.01639924],
                a121.Profile.PROFILE_3: [0.76755397, 0.0119841],
                a121.Profile.PROFILE_4: [0.91310206, 0.01822777],
                a121.Profile.PROFILE_5: [1.05453651, 0.0045255],
            }
        elif temperature < 45:
            OFFSET_COMPENSATION_COEFFS = {
                a121.Profile.PROFILE_1: [0.91880272, 0.01782158],
                a121.Profile.PROFILE_2: [0.59457893, 0.0192985],
                a121.Profile.PROFILE_3: [0.85039166, 0.01478081],
                a121.Profile.PROFILE_4: [1.00348084, 0.02306631],
                a121.Profile.PROFILE_5: [0.98183729, 0.00794888],
            }
        elif temperature < 80:
            OFFSET_COMPENSATION_COEFFS = {
                a121.Profile.PROFILE_1: [0.54980311, 0.00836143],
                a121.Profile.PROFILE_2: [0.49726231, 0.01961523],
                a121.Profile.PROFILE_3: [0.53138948, 0.00784231],
                a121.Profile.PROFILE_4: [0.44605765, 0.01097863],
                a121.Profile.PROFILE_5: [0.51716572, 0.00060455],
            }
        else:
            OFFSET_COMPENSATION_COEFFS = {
                a121.Profile.PROFILE_1: [0.54980311, 0.00836143],
                a121.Profile.PROFILE_2: [0.49726231, 0.01961523],
                a121.Profile.PROFILE_3: [0.53138948, 0.00784231],
                a121.Profile.PROFILE_4: [0.44605765, 0.01097863],
                a121.Profile.PROFILE_5: [0.51716572, 0.00060455],
            }
    else:
        OFFSET_COMPENSATION_COEFFS = {
            a121.Profile.PROFILE_1: [0.91880272, 0.01782158],
            a121.Profile.PROFILE_2: [0.59457893, 0.0192985],
            a121.Profile.PROFILE_3: [0.85039166, 0.01478081],
            a121.Profile.PROFILE_4: [1.00348084, 0.02306631],
            a121.Profile.PROFILE_5: [0.98183729, 0.00794888],
        }

    p = OFFSET_COMPENSATION_COEFFS[profile]
    return p[0] * peak_location + p[1]


def _subsweep_distances(
    subsweep: a121.SubsweepConfig, metadata: a121.Metadata
) -> npt.NDArray[np.float64]:
    points = np.arange(subsweep.num_points) * subsweep.step_length + subsweep.start_point
    distances_m = np.array(points, dtype=float) * metadata.base_step_length_m
    return distances_m


def get_distances_m(
    config: Union[a121.SensorConfig, a121.SubsweepConfig], metadata: a121.Metadata
) -> npt.NDArray[np.float64]:
    """
    Returns an array of all distances measured by the config.
    The distances are returned in the same order as found in the result frame
    (:py:meth:`acconeer.exptool.a121.Result.frame`)
    """

    if isinstance(config, a121.SensorConfig):
        # Go through all subsweeps
        all_distances = []
        for subsweep in config.subsweeps:
            distances_m = _subsweep_distances(subsweep, metadata)
            all_distances += list(distances_m)
        ret = np.array(all_distances)
    else:
        # We are already a subsweep
        ret = _subsweep_distances(config, metadata)

    return ret


def get_approx_fft_vels(
    metadata: a121.Metadata, config: a121.SensorConfig
) -> Tuple[npt.NDArray[np.float64], float]:
    if config.sweep_rate is not None:
        sweep_rate = config.sweep_rate
    else:
        sweep_rate = metadata.max_sweep_rate

    spf = config.sweeps_per_frame
    f_res = 1 / spf
    freqs = np.fft.fftshift(np.fft.fftfreq(spf))
    f_to_v = 2.5e-3 * sweep_rate
    return freqs * f_to_v, f_res * f_to_v


def interpolate_peaks(
    abs_sweep: npt.NDArray[np.float64],
    peak_idxs: list[int],
    start_point: int,
    step_length: int,
    step_length_m: float,
) -> Tuple[list[float], list[float]]:
    """Quadratic interpolation around a peak using the amplitudes of the peak and its two
    neighboring points.

    Derivation:
    https://math.stackexchange.com/questions/680646/get-polynomial-function-from-3-points

    :param abs_sweep: Absolute value of mean sweep.
    :param peak_idxs: List containing indexes of identified peaks.
    :param start_point: Start point.
    :param step_length: Step length in points.
    :param step_length_m: Step length in meters.
    """
    estimated_distances = []
    estimated_amplitudes = []
    for peak_idx in peak_idxs:
        x = np.arange(peak_idx - 1, peak_idx + 2, 1)
        y = abs_sweep[peak_idx - 1 : peak_idx + 2]
        a = (x[0] * (y[2] - y[1]) + x[1] * (y[0] - y[2]) + x[2] * (y[1] - y[0])) / (
            (x[0] - x[1]) * (x[0] - x[2]) * (x[1] - x[2])
        )
        b = (y[1] - y[0]) / (x[1] - x[0]) - a * (x[0] + x[1])
        c = y[0] - a * x[0] ** 2 - b * x[0]
        peak_loc = -b / (2 * a)
        estimated_distances.append((start_point + peak_loc * step_length) * step_length_m)
        estimated_amplitudes.append(a * peak_loc**2 + b * peak_loc + c)
    return estimated_distances, estimated_amplitudes


def calculate_loopback_peak_location(result: a121.Result, config: a121.SensorConfig) -> float:
    """
    Calculate the distance tot peak of the loopback using interpolation.
    """

    (B, A) = get_distance_filter_coeffs(config.profile, config.step_length, narrow_filter=True)
    sweep = np.squeeze(result.frame, axis=0)
    abs_sweep = np.abs(filtfilt(B, A, sweep))
    peak_idx = [int(np.argmax(abs_sweep))]

    (estimated_dist, _) = interpolate_peaks(
        abs_sweep=abs_sweep,
        peak_idxs=peak_idx,
        start_point=config.start_point,
        step_length=config.step_length,
        step_length_m=APPROX_BASE_STEP_LENGTH_M,
    )

    return estimated_dist[0]


def find_peaks(
    abs_sweep: npt.NDArray[np.float64], threshold: npt.NDArray[np.float64]
) -> list[int]:
    """Identifies peaks above threshold.

    A peak is defined as a point with greater value than its two neighboring points and all
    three points are above the threshold.

    :param abs_sweep: Absolute value of mean sweep.
    :param threshold: Array of values, defining the threshold throughout the sweep.
    """
    if threshold is None:
        raise ValueError
    found_peaks = []
    d = 1
    N = len(abs_sweep)
    while d < (N - 1):
        if np.isnan(threshold[d - 1]):
            d += 1
            continue
        if np.isnan(threshold[d + 1]):
            break
        if abs_sweep[d] <= threshold[d]:
            d += 2
            continue
        if abs_sweep[d - 1] <= threshold[d - 1]:
            d += 1
            continue
        if abs_sweep[d - 1] >= abs_sweep[d]:
            d += 1
            continue
        d_upper = d + 1
        while True:
            if (d_upper) >= (N - 1):
                break
            if np.isnan(threshold[d_upper]):
                break
            if abs_sweep[d_upper] <= threshold[d_upper]:
                break
            if abs_sweep[d_upper] > abs_sweep[d]:
                break
            elif abs_sweep[d_upper] < abs_sweep[d]:
                found_peaks.append(int(np.argmax(abs_sweep[d:d_upper]) + d))
                break
            else:
                d_upper += 1
        d = d_upper
    return found_peaks


def get_temperature_adjustment_factors(
    reference_temperature: float, current_temperature: float, profile: a121.Profile
) -> Tuple[float, float]:
    """Calculate temperature compensation for mean sweep and background noise(tx off) standard
    deviation.

    The signal adjustment models how the amplitude level fluctuates with temperature.
    If the same object is measured against while the temperature changes,
    the amplitude level should be multiplied with this factor.
    The temperature difference should be calculated by subtracting
    the (calibration) recorded temperature from the measured.

    Example of usage:
    reference_temperature (recorded temperature during calibration)
    reference_amplitude (recorded amplitude during calibration)

    measurement_temperature (temperature at measurement time)

    signal_adjustment_factor, deviation_adjustment_factor =
    get_temperature_adjustment_factors(reference_temperature, measurement_temperature, profile)

    reference_amplitude_new = reference_amplitude * signal_adjustment_factor

    The reference_amplitude_new is an approximation of what the calibrated amplitude
    would be at the new temperature.

    E.g. When the temperature falls 60 degrees, the amplitude (roughly) doubles.
    This yields a signal_adjustment_factor of (about) 2.

    The signal adjustment model is follows 2 ** (temperature_diff / model_parameter), where
    model_parameter reflects the temperature difference relative the reference temperature,
    required for the amplitude to double/halve.

    The deviation_adjustment_factor works the same way, but is applied to a measurement
    taken with the Tx off. So if instead of measurement_amplitude, we have a measurement of tx_off.
    The procedure for calculating this is to take the same configuration as
    the application will use, but turning off the Tx.
    This calibration value is multiplied with the deviation_adjustment_factor.
    """

    temperature_diff = current_temperature - reference_temperature

    signal_adjustment_factor = 2 ** (
        (temperature_diff / SIGNAL_TEMPERATURE_MODEL_PARAMETER[profile]) * -1
    )
    deviation_adjustment_factor = (
        DEVIATION_TEMPERATURE_MODEL_PARAMETER[0] * temperature_diff
        + DEVIATION_TEMPERATURE_MODEL_PARAMETER[1]
    )
    return (signal_adjustment_factor, deviation_adjustment_factor)


def get_distance_filter_coeffs(
    profile: a121.Profile, step_length: int, narrow_filter: bool = False
) -> Any:
    """Calculates the IIR coefficients corresponding to a matched filter, based on the profile and
    the step length.

    Narrow filter increase the bandwidth of the filter, yielding a less smeared envelope after
    filtering.
    """
    NARROW_FILTER_MULTIPLIER = 2.0
    wnc = APPROX_BASE_STEP_LENGTH_M * step_length / (ENVELOPE_FWHM_M[profile])
    if narrow_filter:
        wnc *= NARROW_FILTER_MULTIPLIER
    return butter(N=1, Wn=wnc)


def get_distance_filter_edge_margin(profile: a121.Profile, step_length: int) -> int:
    """Calculates the number of points required for filter initialization when performing
    distance filtering, using the filter coefficients supplied by the function
    get_distance_filter_coeffs.
    """
    return int(_safe_ceil(ENVELOPE_FWHM_M[profile] / (APPROX_BASE_STEP_LENGTH_M * step_length)))


def double_buffering_frame_filter(
    _frame: npt.NDArray[Any],
) -> Optional[npt.NDArray[np.complex128]]:
    """
    Detects and removes outliers in data that appear when the double buffering mode is enabled,
    and returns the filtered frame.

    Outliers are detected along the sweep dimension using the second order difference. For
    reliable outlier detection, the filter is applied only when there are 32 or more sweeps per frame.

    The disturbance caused by enabling the double buffering mode can appear in multiple sweeps
    but, according to observations, is limited to a maximum of two consecutive sweeps. Therefore, the
    function removes outliers by interpolating between the sample before and the sample two positions
    ahead.

    The function does not correct disturbances that may appear in the initial or final sweeps.
    """

    (n_s, n_d) = _frame.shape
    min_num_sweeps = 32

    if n_s < min_num_sweeps:
        return None

    frame_real = _frame["real"]
    frame_imag = _frame["imag"]

    # Second order difference along sweeps
    frame_diff_real = np.zeros((n_s, n_d), dtype=np.int16)
    frame_diff_imag = np.zeros((n_s, n_d), dtype=np.int16)
    frame_diff_real[1:-1, :] = np.diff(frame_real, axis=0, n=2)
    frame_diff_imag[1:-1, :] = np.diff(frame_imag, axis=0, n=2)

    # Estimating magnitude using: abs(real) + abs(imag)
    frame_diff_abs = np.abs(frame_diff_real) + np.abs(frame_diff_imag)

    # Mean absolute deviation
    frame_diff_mad = np.sum(frame_diff_abs, axis=0) // (n_s - 2)

    # Detect outliers
    threshold = MEAN_ABS_DEV_OUTLIER_TH * frame_diff_mad
    outliers = frame_diff_abs > threshold

    # Perform filtering at each distance to remove outliers
    filtered_frame_real = frame_real.copy()
    filtered_frame_imag = frame_imag.copy()
    for d in range(n_d):
        if np.any(outliers[:, d]):
            args = np.where(outliers[:, d])[0]
            for idx in args:
                if idx <= 1:
                    # Median filtering for the first two and the last two sweeps
                    filtered_frame_real[idx, d] = np.median(filtered_frame_real[idx : idx + 4, d])
                    filtered_frame_imag[idx, d] = np.median(filtered_frame_imag[idx : idx + 4, d])
                elif idx >= n_s - 2:
                    filtered_frame_real[idx, d] = np.median(filtered_frame_real[idx - 3 : idx, d])
                    filtered_frame_imag[idx, d] = np.median(filtered_frame_imag[idx - 3 : idx, d])
                else:
                    # Interpolation for the remaining sweeps
                    filtered_frame_real[idx, d] = int(
                        (
                            2 * filtered_frame_real[max(idx - 1, 0), d]
                            + filtered_frame_real[min(idx + 2, n_s - 1), d]
                        )
                        / 3
                    )
                    filtered_frame_imag[idx, d] = int(
                        (
                            2 * filtered_frame_imag[max(idx - 1, 0), d]
                            + filtered_frame_imag[min(idx + 2, n_s - 1), d]
                        )
                        / 3
                    )

    filtered_frame = np.empty((n_s, n_d), dtype=np.complex128)
    filtered_frame.real = filtered_frame_real
    filtered_frame.imag = filtered_frame_imag

    return filtered_frame


def select_prf_m(distance_m: float, profile: a121.Profile) -> a121.PRF:
    """Calculates the highest possible PRF for the given breakpoint.

    :param distance_m: Distance in meters
    :param profile: Profile.
    """
    max_meas_dist_m = copy.copy(MAX_MEASURABLE_DIST_M)

    if a121.PRF.PRF_19_5_MHz in max_meas_dist_m and profile != a121.Profile.PROFILE_1:
        del max_meas_dist_m[a121.PRF.PRF_19_5_MHz]

    viable_prfs = [prf for prf, max_dist_m in max_meas_dist_m.items() if distance_m < max_dist_m]
    return sorted(viable_prfs, key=lambda prf: prf.frequency)[-1]


def select_prf(breakpoint: int, profile: a121.Profile) -> a121.PRF:
    """Calculates the highest possible PRF for the given breakpoint.

    :param breakpoint: Distance in the unit of points.
    :param profile: Profile.
    """
    return select_prf_m(breakpoint * APPROX_BASE_STEP_LENGTH_M, profile)


def get_max_profile_without_direct_leakage(start_m: float) -> a121.Profile:
    """
    Returns the highest possible profile such that
    the direct leakage for that profile doesn't include the start_m distance.
    If all direct leakages is inside the distance, return profile_1.
    """
    envelope_fwhm_m_reversed = dict(reversed(list(ENVELOPE_FWHM_M.items())))
    for profile, fwhm in envelope_fwhm_m_reversed.items():
        if fwhm * 2.0 <= start_m:
            return profile
    return a121.Profile.PROFILE_1


def get_max_step_length(profile: a121.Profile) -> int:
    """
    Calculate biggest possible step length based on the fwhm of the set profile.
    Achieve detection on the complete range with minimum number of sampling points.
    """
    fwhm_p = ENVELOPE_FWHM_M[profile] / APPROX_BASE_STEP_LENGTH_M
    if fwhm_p < SPARSE_IQ_PPC:
        step_length = SPARSE_IQ_PPC // int(np.ceil(SPARSE_IQ_PPC / fwhm_p))
    else:
        step_length = int((fwhm_p // SPARSE_IQ_PPC) * SPARSE_IQ_PPC)
    return step_length


def estimate_frame_rate(client: a121.Client, session_config: a121.SessionConfig) -> float:
    """
    Performs a measurement of the actual frame rate obtained by the configuration.
    This is hardware dependent. Hence the solution using a measurement.

    If a recorder is attached to the client,
    this call will result in a new session being run and recorded!
    """

    delta_times = np.full(2, np.nan)

    client.setup_session(session_config)
    client.start_session()

    for i in range(4):
        result = client.get_next()
        assert isinstance(result, a121.Result)

        if i < 2:
            # Ignore first read, it is sometimes inaccurate
            last_time = result.tick_time
            continue

        time = result.tick_time
        delta = time - last_time
        last_time = time
        delta_times = np.roll(delta_times, -1)
        delta_times[-1] = delta

    client.stop_session()

    return float(1.0 / np.nanmean(delta_times))


def exponential_smoothing_coefficient(fs: float, time_constant: float) -> float:
    """Calculate the exponential smoothing coefficient.

    Typical usage:

    y = y * coeff + x * (1 - coeff)

    :param fs: Sampling frequency.
    :param time_constant: Time constant.
    """
    dt = 1 / fs
    return float(np.exp(-dt / time_constant))


def _safe_ceil(x: float) -> float:
    """Perform safe ceil.

    Implementation of ceil function, compatible with float representation in C.
    """
    return float(f"{x:.16g}")


def calc_processing_gain(profile: a121.Profile, step_length: int) -> float:
    """
    Approximates the processing gain of the matched filter.
    """
    envelope_base_length_m = ENVELOPE_FWHM_M[profile] * 2  # approx envelope width
    num_points_in_envelope = (
        int(envelope_base_length_m / (step_length * APPROX_BASE_STEP_LENGTH_M)) + 2
    )
    mid_point = num_points_in_envelope // 2
    pulse = np.concatenate(
        (
            np.linspace(0, 1, mid_point),
            np.linspace(1, 0, num_points_in_envelope - mid_point),
        )
    )
    return float(np.sum(pulse**2))


def _convert_multiple_amplitudes_to_strengths(
    amplitudes: list[float],
    distances: list[float],
    subsweeps: list[a121.SubsweepConfig],
    bg_noise_std: list[float],
    reflector_shape: ReflectorShape,
) -> list[float]:
    # Determine subsweep breakpoints in meters.
    start_points = [subsweep.start_point for subsweep in subsweeps]
    bpts_m = np.array(start_points) * APPROX_BASE_STEP_LENGTH_M

    strengths = []
    # Loop over amplitude/distance pairs.
    for amplitude, distance in zip(amplitudes, distances):
        # For the current distance, get corresponding sensor parameters and background noise.
        subsweep_idx = np.sum(bpts_m < distance) - 1
        subsweep_config = subsweeps[subsweep_idx]
        sigma = bg_noise_std[subsweep_idx]

        # Calculate strengths.
        strengths.append(
            _convert_amplitude_to_strength(
                subsweep_config, amplitude, distance, sigma, reflector_shape
            )
        )

    return strengths


def _convert_amplitude_to_strength(
    subsweep_config: a121.SubsweepConfig,
    amplitude: float,
    distance: float,
    bg_noise_std: float,
    reflector_shape: ReflectorShape = ReflectorShape.GENERIC,
) -> float:
    processing_gain_db = 10 * np.log10(
        calc_processing_gain(subsweep_config.profile, subsweep_config.step_length)
    )
    s_db = 20 * np.log10(amplitude)
    n_db = 20 * np.log10(bg_noise_std)
    r_db = reflector_shape.exponent * 10 * np.log10(distance)
    rlg_db = RLG_PER_HWAAS_MAP[subsweep_config.profile] + 10 * np.log10(subsweep_config.hwaas)

    return float(s_db - n_db - rlg_db + r_db - processing_gain_db)
