# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import copy
from typing import Any, Tuple

import numpy as np
import numpy.typing as npt
from scipy.signal import butter

from acconeer.exptool import a121


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
MAX_MEASURABLE_DIST_M = {
    a121.PRF.PRF_19_5_MHz: 3.1,
    a121.PRF.PRF_15_6_MHz: 5.8,
    a121.PRF.PRF_13_0_MHz: 7.0,
    a121.PRF.PRF_8_7_MHz: 12.7,
    a121.PRF.PRF_6_5_MHz: 18.5,
    a121.PRF.PRF_5_2_MHz: 28.8,
}
# Slope and interception of linear noise temperature model.
NOISE_TEMPERATURE_MODEL_PARAMETER = [-0.00275, 0.98536]

SPEED_OF_LIGHT = 299792458
RADIO_FREQUENCY = 60.5e9
WAVELENGTH = SPEED_OF_LIGHT / RADIO_FREQUENCY
PERCEIVED_WAVELENGTH = WAVELENGTH / 2


def get_distances_m(
    config: a121.SensorConfig,
    metadata: a121.Metadata,
) -> Tuple[npt.NDArray[np.float_], float]:
    points = np.arange(config.num_points) * config.step_length + config.start_point
    distances_m = points * metadata.base_step_length_m
    step_length_m = config.step_length * metadata.base_step_length_m
    return distances_m, step_length_m


def get_approx_sweep_rate(config: a121.SensorConfig) -> float:
    ppp = {1: 24, 2: 20, 3: 16, 4: 16, 5: 16}[config.profile.value]

    n = 3 * ppp + config.num_points * config.hwaas * ppp

    return config.prf.frequency / n


def get_approx_fft_vels(config: a121.SensorConfig) -> Tuple[npt.NDArray, float]:
    sweep_rate = get_approx_sweep_rate(config)
    if config.sweep_rate is not None:
        sweep_rate = min([sweep_rate, config.sweep_rate])

    spf = config.sweeps_per_frame
    f_res = 1 / spf
    freqs = np.fft.fftshift(np.fft.fftfreq(spf))  # type: ignore[call-overload]
    f_to_v = 2.5e-3 * sweep_rate
    return freqs * f_to_v, f_res * f_to_v


def interpolate_peaks(
    abs_sweep: npt.NDArray[np.float_],
    peak_idxs: list[int],
    start_point: int,
    step_length: int,
    step_length_m: float,
) -> Tuple[list[float], list[float]]:
    """Quadratic interpolation around a peak using the amplitudes of the peak and its two
    neghbouring points.

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


def find_peaks(abs_sweep: npt.NDArray[np.float_], threshold: npt.NDArray[np.float_]) -> list[int]:
    """Identifies peaks above threshold.

    A peak is defined as a point with greater value than its two neighbouring points and all
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
    temperature_diff: int, profile: a121.Profile
) -> Tuple[float, float]:
    """Calculate temperature compensation for mean sweep and background noise(tx off) standard
    deviation.

    The signal adjustment model is follows 2 ** (temperature_diff / model_parameter), where
    model_parameter reflects the temperature difference relative the reference temperature,
    required for the amplitude to double/halve.

    The noise adjustment is a linear function of the temperature difference, calibrated using
    noise-normalized data, generalizing to different sensor configurations.
    """
    signal_adjustment_factor = 2 ** (
        temperature_diff / SIGNAL_TEMPERATURE_MODEL_PARAMETER[profile]
    )
    noise_adjustment_factor = (
        NOISE_TEMPERATURE_MODEL_PARAMETER[0] * temperature_diff
        + NOISE_TEMPERATURE_MODEL_PARAMETER[1]
    )
    return (signal_adjustment_factor, noise_adjustment_factor)


def get_distance_filter_coeffs(profile: a121.Profile, step_length: int) -> Any:
    """Calculates the iir coefficients corresponding to a matched filter, based on the profile and
    the step length.
    """
    wnc = APPROX_BASE_STEP_LENGTH_M * step_length / (ENVELOPE_FWHM_M[profile])
    return butter(N=2, Wn=wnc)


def get_distance_filter_edge_margin(profile: a121.Profile, step_length: int) -> int:
    """Calculates the number of points required for filter initialization when performing
    distance filtering, using the filter coefficients supplied by the function
    get_distance_filter_coeffs.
    """
    return int(_safe_ceil(ENVELOPE_FWHM_M[profile] / (APPROX_BASE_STEP_LENGTH_M * step_length)))


def select_prf(breakpoint: int, profile: a121.Profile) -> a121.PRF:
    """Calculates the highest possible PRF for the given breakpoint.

    :param breakpoint: Distance in the unit of points.
    :param profile: Profile.
    """
    max_meas_dist_m = copy.copy(MAX_MEASURABLE_DIST_M)

    if a121.PRF.PRF_19_5_MHz in max_meas_dist_m and profile != a121.Profile.PROFILE_1:
        del max_meas_dist_m[a121.PRF.PRF_19_5_MHz]

    breakpoint_m = breakpoint * APPROX_BASE_STEP_LENGTH_M
    viable_prfs = [prf for prf, max_dist_m in max_meas_dist_m.items() if breakpoint_m < max_dist_m]
    return sorted(viable_prfs, key=lambda prf: prf.frequency)[-1]


def _safe_ceil(x: float) -> float:
    """Perform safe ceil.

    Implementation of ceil function, compatible with float representation in C.
    """
    return float(f"{x:.16g}")
