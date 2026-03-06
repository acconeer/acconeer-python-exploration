# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    RLG_PER_HWAAS_MAP,
    ReflectorShape,
    calc_processing_gain,
    get_temperature_adjustment_factors,
)


# Type definitions
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]


def sensitivity_to_standard_deviations(sensitivity: float) -> float:
    """Convert sensitivity to standard deviations used by recorded threshold and CFAR.

    0 sensitivity corresponds to 8 standard deviations. 1 sensitivity corresponds to 1
    standard deviation.
    """
    if sensitivity < 0.0 or sensitivity > 1.0:
        msg = "Sensitivity outside of valid interval (0.0 <= Sensitivity <= 1.0)."
        raise ValueError(msg)

    return 8.0 - 7.0 * sensitivity


class Threshold(ABC):
    """Decision rule for thresholding an input array."""

    def compute(self, abs_sweep: FloatArray, temperature: int) -> FloatArray:
        """Compute the threshold values based on abs_sweep and temperature."""
        threshold_values = self._calculate_threshold_values(abs_sweep, temperature)

        # Optional: Sanity check
        if np.any(threshold_values < 0):
            msg = "Threshold_values must be non-negative"
            raise ValueError(msg)

        # Ensure same type as abs_sweep
        if not isinstance(threshold_values, type(abs_sweep)):
            msg = f"Expected threshold_values to be {FloatArray}, got {type(threshold_values)}"
            raise TypeError(msg)

        # Ensure same shape as abs_sweep
        if threshold_values.shape != abs_sweep.shape:
            msg = (
                f"Expected threshold_values shape {abs_sweep.shape}, got {threshold_values.shape}"
            )
            raise ValueError(msg)

        return threshold_values

    @property
    def margin(self) -> int:
        """Default margin is 0 samples, subclasses can override."""
        return 0

    @abstractmethod
    def _calculate_threshold_values(self, abs_sweep: FloatArray, temperature: int) -> FloatArray:
        """To be implemented by subclasses.

        Calculate/update the threshold values based on abs_sweep and temperature.
        The returned threshold_values must have the same shape as abs_sweep.
        """
        raise NotImplementedError


class FixedThreshold(Threshold):
    """A fixed (precomputed) threshold (constant)."""

    def __init__(self, fixed_value: float) -> None:
        self._fixed_value: float = fixed_value

    def _calculate_threshold_values(self, abs_sweep: FloatArray, temperature: int) -> FloatArray:
        return np.full(shape=abs_sweep.shape, fill_value=self._fixed_value, dtype=np.float64)


class FixedStrengthThreshold(Threshold):
    """Calculates the threshold corresponding to a given RCS."""

    def __init__(
        self,
        fixed_strength: float,
        bg_noise_std_per_subsweep: list[float],
        reflector_shape: ReflectorShape,
        profile: a121.Profile,
        step_length: int,
        distance_points: npt.NDArray[np.intp],
        start_points: list[int],
        hwaas_per_subsweep: list[int],
    ) -> None:
        self.fixed_strength: float = fixed_strength
        self.bg_noise_std_per_subsweep: list[float] = bg_noise_std_per_subsweep
        self.reflector_shape: ReflectorShape = reflector_shape
        self.profile = profile
        self.step_length = step_length
        self.distance_points = distance_points
        self.start_points = start_points
        self.hwaas_per_subsweep = hwaas_per_subsweep
        self.processing_gain: float = calc_processing_gain(self.profile, self.step_length)
        self.processing_gain_db: float = 10 * np.log10(self.processing_gain)

    def _calculate_threshold_values(self, abs_sweep: FloatArray, temperature: int) -> FloatArray:
        if len(abs_sweep) > len(self.distance_points):
            msg = (
                f"abs_sweep length ({len(abs_sweep)}) exceeds available distance points "
                f"({len(self.distance_points)}). Subsweep configuration does not match the processed sweep."
            )
            raise ValueError(msg)

        threshold_values = []
        for distance_point in self.distance_points:
            distance_m = distance_point * APPROX_BASE_STEP_LENGTH_M

            if distance_m > 0.0:
                subsweep_index = int(np.sum(np.array(self.start_points) < distance_point) - 1)
                sigma = self.bg_noise_std_per_subsweep[subsweep_index]
                hwaas = self.hwaas_per_subsweep[subsweep_index]

                n_db = 20 * np.log10(sigma)
                r_db = self.reflector_shape.exponent * 10 * np.log10(distance_m)
                rlg_db = RLG_PER_HWAAS_MAP[self.profile] + 10 * np.log10(hwaas)

                threshold_values.append(
                    10
                    ** (
                        (self.processing_gain_db + n_db + rlg_db - r_db + self.fixed_strength) / 20
                    )
                )

            else:
                threshold_values.append(0.0)

        return np.array(threshold_values, dtype=abs_sweep.dtype)


class RecordedThreshold(Threshold):
    def __init__(
        self,
        recorded_mean_sweep: FloatArray,
        rec_noise_std_per_subsweep: list[np.float64],
        bg_noise_std_per_subsweep: list[float],
        reference_temperature: int,
        sensitivity: float,
        profile: a121.Profile,
        subsweep_slices_cropped: list[slice],
    ) -> None:
        self.recorded_mean_sweep = recorded_mean_sweep
        self.bg_noise_std_per_subsweep = bg_noise_std_per_subsweep
        self.rec_noise_std_per_subsweep = rec_noise_std_per_subsweep
        self.reference_temperature = reference_temperature
        self.sensitivity = sensitivity
        self.profile = profile
        self.subsweep_slices = subsweep_slices_cropped

    @property
    def num_stds(self) -> float:
        return sensitivity_to_standard_deviations(self.sensitivity)

    def _calculate_threshold_values(self, abs_sweep: FloatArray, temperature: int) -> FloatArray:
        """Updates the recorded threshold to account for temperature effects.

        The threshold is constructed by adding a number of standard deviations of the background
        noise(tx off) and the signal noise (calculated during calibration) to the mean sweep. The
        mean sweep is adjusted by a factor and the background noise is adjusted before fed to this
        method to account for the temperature effect.
        """
        signal_adjustment_factor, noise_adjustment_factor = get_temperature_adjustment_factors(
            reference_temperature=self.reference_temperature,
            current_temperature=temperature,
            profile=self.profile,
        )

        threshold_values = signal_adjustment_factor * self.recorded_mean_sweep.copy()
        for subsweep_index, subsweep_slice in enumerate(self.subsweep_slices):
            bg_noise_std = self.bg_noise_std_per_subsweep[subsweep_index]
            rec_noise_std = self.rec_noise_std_per_subsweep[subsweep_index]
            abs_noise_std = np.sqrt(
                noise_adjustment_factor * bg_noise_std**2
                + threshold_values[subsweep_slice] ** 2 * rec_noise_std**2
            )
            threshold_values[subsweep_slice] += self.num_stds * abs_noise_std

        return threshold_values


class CfarThreshold(Threshold):
    # Tuning constants
    GUARD_LENGTH_ADJUSTMENT = 4
    WINDOW_LENGTH_ADJUSTMENT = 0.25
    ONE_SIDED_ENV_WIDTH_MULTIPLIER = 3.0  # used for one-sided breakpoint

    @classmethod
    def _calc_window_length(cls, profile: a121.Profile, step_length: int) -> int:
        """Calculates the CFAR window length to use in samples."""
        step_length_m = APPROX_BASE_STEP_LENGTH_M * step_length
        window_length_m = ENVELOPE_FWHM_M[profile] * cls.WINDOW_LENGTH_ADJUSTMENT
        window_length = int(window_length_m / step_length_m)
        return max([1, window_length])

    @classmethod
    def _calc_guard_half_length(cls, profile: a121.Profile, step_length: int) -> int:
        """Calculates the CFAR guard length to use in samples."""
        step_length_m = APPROX_BASE_STEP_LENGTH_M * step_length
        guard_length_m = ENVELOPE_FWHM_M[profile] * cls.GUARD_LENGTH_ADJUSTMENT
        guard_half_length_m = guard_length_m / 2
        guard_half_length = int(guard_half_length_m / step_length_m)
        return guard_half_length

    @classmethod
    def calc_margin(cls, profile: a121.Profile, step_length: int) -> int:
        """Calculates the total CFAR margin in samples."""
        window_length = cls._calc_window_length(profile, step_length)
        guard_length = cls._calc_guard_half_length(profile, step_length)
        return window_length + guard_length

    def __init__(
        self,
        sensitivity: float,
        bg_noise_std_per_subsweep: Optional[list[float]],
        profile: a121.Profile,
        start_point: int,
        step_length: int,
        subsweep_slices_cropped: list[slice],
    ) -> None:
        self.sensitivity = sensitivity
        self.bg_noise_std_per_subsweep = bg_noise_std_per_subsweep
        self.profile = profile
        self.start_point = start_point
        self.step_length = step_length
        self.subsweep_slices = subsweep_slices_cropped

    @property
    def window_length(self) -> int:
        return self._calc_window_length(self.profile, self.step_length)

    @property
    def guard_half_length(self) -> int:
        return self._calc_guard_half_length(self.profile, self.step_length)

    @property
    def margin(self) -> int:
        return self.calc_margin(self.profile, self.step_length)

    @property
    def one_sided_breakpoint_in_sweep(self) -> int | None:
        """Index (in full-sweep point coordinates) up to which CFAR is one-sided."""
        # breakpoint_lim defines at what distance cfar should go from being calculated
        # one-sided to symmetrical. One-sided is used to avoid introducing the direct leakage
        # in the threshold. The limit is based on a multiple of the envelope width.
        env_width_m = ENVELOPE_FWHM_M[a121.Profile.PROFILE_1]
        scaled_env_width_m = self.ONE_SIDED_ENV_WIDTH_MULTIPLIER * env_width_m
        scaled_env_width = int(round(scaled_env_width_m / APPROX_BASE_STEP_LENGTH_M))
        breakpoint_lim = scaled_env_width + self.margin

        if breakpoint_lim < self.start_point:
            return None

        # Convert absolute point to local index in this sweep
        return ((breakpoint_lim - self.start_point) // self.step_length) + 1

    @property
    def num_stds(self) -> float:
        return sensitivity_to_standard_deviations(self.sensitivity)

    def _calculate_threshold_values(self, abs_sweep: FloatArray, temperature: int) -> FloatArray:
        """Calculate CFAR threshold over `abs_sweep`.

        Each point of the threshold is formed by using data from neighboring segments of the
        sweep.

        The distance between a point and the start of the neighboring segment is determined by
        the guard half length. The width of the segment by the window length.

        For each point, the threshold is calculated as the average of the points located in the
        segments to the left and to the right.

        One-sided threshold is applied for all points below one_sided_breakpoint_in_sweep. The
        purpose is to avoid the influence of direct leakage in the threshold.
        """
        # Moving average ("valid" reduces length by window_length-1)
        window = np.ones(self.window_length, dtype=abs_sweep.dtype)
        filtered_abs_sweep = np.convolve(abs_sweep, window, mode="valid") / self.window_length

        # Number of points where threshold is defined (cropped region)
        n_valid = abs_sweep.shape[0] - 2 * self.margin

        left_cfar_component = filtered_abs_sweep[:n_valid] / 2.0
        right_cfar_component = filtered_abs_sweep[-n_valid:] / 2.0

        bp = self.one_sided_breakpoint_in_sweep
        if bp is not None:
            left_cfar_component[:bp] = 0.0

        threshold_values = np.full(abs_sweep.shape, np.nan, dtype=abs_sweep.dtype)
        threshold_values[self.margin : -self.margin] = left_cfar_component + right_cfar_component

        # Add noise-dependent term
        if self.bg_noise_std_per_subsweep is not None:
            for subsweep_index, subsweep_slice in enumerate(self.subsweep_slices):
                bg_noise_std = self.bg_noise_std_per_subsweep[subsweep_index]
                threshold_values[subsweep_slice] += self.num_stds * bg_noise_std

        return threshold_values
