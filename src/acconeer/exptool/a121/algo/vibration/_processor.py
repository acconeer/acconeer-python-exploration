# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import enum
from typing import Optional

import attrs
import h5py
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import (
    attrs_ndarray_isclose,
    attrs_optional_ndarray_isclose,
)
from acconeer.exptool.a121.algo import (
    PERCEIVED_WAVELENGTH,
    AlgoParamEnum,
    AlgoProcessorConfigBase,
    ProcessorBase,
    double_buffering_frame_filter,
)
from acconeer.exptool.utils import is_power_of_2


class ReportedDisplacement(AlgoParamEnum):
    """Selects how displacement is reported."""

    AMPLITUDE = enum.auto()
    """Report displacement as amplitude."""

    PEAK2PEAK = enum.auto()
    """Report displacement as peak to peak."""


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    time_series_length: int = attrs.field(default=1024)
    """Length of time series."""

    lp_coeff: float = attrs.field(default=0.95)
    """Specify filter coefficient of exponential filter."""

    threshold_margin: float = attrs.field(default=10.0)
    """Specify threshold margin (micro meter)."""

    amplitude_threshold: float = attrs.field(default=100.0)
    """Specify minimum amplitude for calculating vibration."""

    reported_displacement_mode: ReportedDisplacement = attrs.field(
        default=ReportedDisplacement.AMPLITUDE,
        converter=ReportedDisplacement,
    )
    """Selects whether to report the amplitude or peak to peak of the estimated frequency."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if not is_power_of_2(self.time_series_length):
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "time_series_length",
                    "Should be power of 2 for efficient usage of fast fourier transform",
                )
            )

        if config.sensor_config.sweep_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "sweep_rate",
                    "Must be set",
                )
            )

        if config.sensor_config.num_points != 1:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config.subsweep,
                    "num_points",
                    "Must be set to 1",
                )
            )

        if (
            config.sensor_config.continuous_sweep_mode
            and not config.sensor_config.double_buffering
        ):
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "continuous_sweep_mode",
                    "Continuous sweep mode requires double buffering to be enabled",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    amplitude_threshold: float
    """Amplitude threshold."""

    zm_time_series: Optional[npt.NDArray[np.float_]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    """Time series being analyzed."""

    lp_displacements_threshold: Optional[npt.NDArray[np.float_]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    """Threshold used for detecting significant frequencies."""


@attrs.frozen(kw_only=True)
class ProcessorResult:
    max_sweep_amplitude: float
    """Max amplitude in sweep.

    Used to determine whether an object is in front of the sensor.
    """

    lp_displacements: Optional[npt.NDArray[np.float_]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    """Array of estimated displacement (um) per frequency."""

    lp_displacements_freqs: npt.NDArray[np.float_] = attrs.field(eq=attrs_ndarray_isclose)
    """Array of frequencies where displacement is estimated (Hz)."""

    max_displacement: Optional[float] = attrs.field(default=None)
    """Largest detected displacement (um)."""

    max_displacement_freq: Optional[float] = attrs.field(default=None)
    """Frequency of largest detected displacement (Hz)."""

    time_series_std: Optional[float] = attrs.field(default=None)
    """Time series std(standard deviation)."""

    extra_result: ProcessorExtraResult
    """Extra result, used for plotting only."""


class Processor(ProcessorBase[ProcessorResult]):

    _WINDOW_BASE_LENGTH = 10
    _HALF_GUARD_BASE_LENGTH = 5
    _CFAR_MARGIN = _WINDOW_BASE_LENGTH + _HALF_GUARD_BASE_LENGTH

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        # Check sensor config and processor config
        assert sensor_config.sweep_rate is not None
        processor_config.validate(sensor_config)

        # Constants
        self.continuous_data_acquisition = (
            sensor_config.double_buffering & sensor_config.continuous_sweep_mode
        )
        self.lp_coeffs = processor_config.lp_coeff
        self.sensitivity = processor_config.threshold_margin
        self.time_series_length = processor_config.time_series_length
        self.amplitude_threshold = processor_config.amplitude_threshold
        self.spf = sensor_config.sweeps_per_frame
        self.reported_displacement_mode = processor_config.reported_displacement_mode

        if self.continuous_data_acquisition:
            self.psd_to_radians_conversion_factor = 2.0 / float(self.time_series_length)
        else:
            self.psd_to_radians_conversion_factor = 2.0 / float(self.spf)

        self.radians_to_displacement = PERCEIVED_WAVELENGTH * 10**6 / (2 * np.pi)

        self.freq = np.fft.rfftfreq(
            processor_config.time_series_length,
            1 / sensor_config.sweep_rate,
        )[1:]

        # Variables
        self.time_series = np.zeros(shape=processor_config.time_series_length)
        self.lp_displacements = np.zeros_like(self.freq)

        self.has_init = False

    def process(self, result: a121.Result) -> ProcessorResult:

        # Determine if an object is in front of the sensor
        max_sweep_amplitude = float(np.max(np.abs(result.frame)))

        if max_sweep_amplitude < self.amplitude_threshold:
            self.has_init = False
            # No object found -> Return
            return ProcessorResult(
                max_sweep_amplitude=max_sweep_amplitude,
                lp_displacements_freqs=self.freq,
                extra_result=ProcessorExtraResult(
                    amplitude_threshold=self.amplitude_threshold,
                ),
            )

        # Handle frame based on whether or not continuous sweep mode is used
        if self.continuous_data_acquisition:
            filter_output = double_buffering_frame_filter(result._frame)
            if filter_output is None:
                frame = result.frame
            else:
                frame = filter_output
            self.time_series = np.roll(self.time_series, -self.spf)
            self.time_series[-self.spf :] = np.angle(frame.squeeze(axis=1))
            self.time_series = np.unwrap(self.time_series)
        else:
            frame = result.frame
            self.time_series = np.unwrap(np.angle(frame.squeeze(axis=1)))

        # Calculate zero mean time series
        zm_time_series = self.time_series - np.mean(self.time_series)

        # Estimate displacement per frequency
        z_abs = np.abs(
            np.fft.rfft(
                zm_time_series,
                n=self.time_series_length,
            )
        )[1:]

        if self.reported_displacement_mode is ReportedDisplacement.AMPLITUDE:
            displacements = (
                z_abs * self.psd_to_radians_conversion_factor * self.radians_to_displacement
            )
        elif self.reported_displacement_mode is ReportedDisplacement.PEAK2PEAK:
            displacements = (
                z_abs * self.psd_to_radians_conversion_factor * self.radians_to_displacement * 2.0
            )
        else:
            raise RuntimeError("Invalid reported displacement")

        if not self.has_init:
            self.lp_displacements = displacements
            self.has_init = True
        else:
            self.lp_displacements = self.lp_displacements * self.lp_coeffs + displacements * (
                1 - self.lp_coeffs
            )

        # Convert time series to um and calculate std
        zm_time_series_um = zm_time_series * self.radians_to_displacement
        time_series_rms = np.sqrt(np.mean(zm_time_series_um**2))

        # Identify peaks in spectrum
        lp_displacements_threshold = self._calculate_cfar_threshold(
            self.lp_displacements,
            self.sensitivity,
            self._WINDOW_BASE_LENGTH,
            self._HALF_GUARD_BASE_LENGTH,
        )

        lp_displacements_threshold = self._extend_cfar_threshold(lp_displacements_threshold)

        # Compare displacements to threshold and exclude first point as it does not form a peak
        idx_over_threshold = (
            np.where(lp_displacements_threshold[1:] < self.lp_displacements[1:])[0] + 1
        )

        if len(idx_over_threshold) != 0:
            displacements_over_threshold = self.lp_displacements[idx_over_threshold]
            max_displacement = np.max(displacements_over_threshold)
            max_displacement_freq = self.freq[
                idx_over_threshold[np.argmax(displacements_over_threshold)]
            ]
        else:
            max_displacement = None
            max_displacement_freq = None

        return ProcessorResult(
            time_series_std=time_series_rms,
            lp_displacements_freqs=self.freq,
            lp_displacements=self.lp_displacements,
            max_sweep_amplitude=max_sweep_amplitude,
            max_displacement=max_displacement,
            max_displacement_freq=max_displacement_freq,
            extra_result=ProcessorExtraResult(
                zm_time_series=zm_time_series_um,
                amplitude_threshold=self.amplitude_threshold,
                lp_displacements_threshold=lp_displacements_threshold,
            ),
        )

    @classmethod
    def _extend_cfar_threshold(cls, threshold: npt.NDArray[np.float_]) -> npt.NDArray[np.float_]:
        """Extends CFAR threshold using extrapolation

        The head of the threshold is extended using linear extrapolation, based on the first points
        of the original threshold.

        The tail of the threshold is extended using the average of the last threshold values of the
        original threshold.
        """
        head_slope_multiplier = 2.0
        head_slope_calculation_width = 3
        tail_mean_calculation_width = 10

        # Extend head
        base_offset = threshold[cls._CFAR_MARGIN]
        mean_slope = (
            np.mean(
                np.diff(
                    threshold[cls._CFAR_MARGIN : cls._CFAR_MARGIN + head_slope_calculation_width]
                )
            )
            * head_slope_multiplier
        )
        threshold[: cls._CFAR_MARGIN] = base_offset + mean_slope * np.arange(-cls._CFAR_MARGIN, 0)

        # Extend tail
        threshold[-cls._CFAR_MARGIN :] = np.mean(
            threshold[-cls._CFAR_MARGIN - tail_mean_calculation_width : -cls._CFAR_MARGIN]
        )

        return threshold

    @staticmethod
    def _calculate_cfar_threshold(
        psd: npt.NDArray[np.float_],
        sensitivity: float,
        window_length: int,
        half_guard_length: int,
    ) -> npt.NDArray[np.float_]:
        threshold = np.full(psd.shape, np.nan)
        margin = window_length + half_guard_length
        length_after_filtering = psd.shape[0] - 2 * margin

        filt_psd = np.convolve(psd, np.ones(window_length), "valid") / window_length
        threshold[margin:-margin] = (
            filt_psd[:length_after_filtering] + filt_psd[-length_after_filtering:]
        ) / 2 + sensitivity
        return threshold


def get_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        profile=a121.Profile.PROFILE_3,
        hwaas=16,
        num_points=1,
        step_length=1,
        start_point=80,
        receiver_gain=10,
        sweep_rate=2000,
        sweeps_per_frame=50,
        double_buffering=True,
        continuous_sweep_mode=True,
        inter_frame_idle_state=a121.IdleState.READY,
        inter_sweep_idle_state=a121.IdleState.READY,
    )


def _load_algo_data(algo_group: h5py.Group) -> ProcessorConfig:
    processor_config = ProcessorConfig.from_json(algo_group["processor_config"][()])
    return processor_config
