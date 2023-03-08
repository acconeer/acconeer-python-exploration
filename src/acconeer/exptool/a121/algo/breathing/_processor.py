# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt
from scipy import signal

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    AlgoProcessorConfigBase,
    ProcessorBase,
)


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    time_series_length: int = attrs.field(default=1024)
    """Length of time series."""

    lp_coeff: float = attrs.field(default=0.75)
    """Specify filter coefficient for exponential filter of psd over time."""

    min_freq: float = attrs.field(default=0.2)
    """Lower limit of bandpass filter."""

    max_freq: float = attrs.field(default=3.0)
    """Upper limit of bandpass filter."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if config.sensor_config.frame_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "frame_rate",
                    "Must be set",
                )
            )

        if config.sensor_config.sweeps_per_frame != 1:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "sweeps_per_frame",
                    "Must be equal to 1",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorResult:
    time_series: npt.NDArray[np.float_]
    distance_to_analyze_m: float
    freqs: npt.NDArray[np.float_]
    lp_psd: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    breathing_rate: Optional[float] = attrs.field(default=None)
    fft_peak_location: Optional[float] = attrs.field(default=None)


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):

    _IIR_INIT_LENGTH: int = 200
    _OVER_SAMPLING_FACTOR: int = 5
    _PHASE_TO_MM: float = APPROX_BASE_STEP_LENGTH_M / (np.pi * 2.0)
    _SECONDS_PER_MINUTE: float = 60.0
    _SECONDS_PER_FFT_WINDOW: float = 10.0
    _AMPL_LP_COEFF: float = 0.99

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        processor_config.validate(sensor_config)

        assert sensor_config.frame_rate is not None
        self.frame_rate = sensor_config.frame_rate
        self.start_point = sensor_config.start_point
        self.step_length = sensor_config.step_length
        self.spf = sensor_config.sweeps_per_frame

        self.time_series_len = processor_config.time_series_length
        self.max_freq = processor_config.max_freq
        self.lp_coeff = processor_config.lp_coeff

        self.time_series = np.zeros(
            shape=(
                processor_config.time_series_length + self._IIR_INIT_LENGTH,
                sensor_config.num_points,
            )
        )

        self.has_init = False

        self.ampl_lp_filt = np.zeros(shape=sensor_config.num_points)

        self.lp_psd = None
        self.window_length = self._SECONDS_PER_FFT_WINDOW * self.frame_rate
        (self.B, self.A) = signal.butter(
            N=2,
            Wn=[processor_config.min_freq, processor_config.max_freq],
            fs=sensor_config.frame_rate,
            btype="bandpass",
        )

    def process(self, result: a121.Result) -> ProcessorResult:
        # Add new data to fifo buffer, unwrap and filter.
        self.time_series = np.roll(self.time_series, -self.spf, axis=0)
        self.time_series[-self.spf :] = np.angle(result.frame)
        time_series_unwrapped = np.unwrap(self.time_series, axis=0) * self._PHASE_TO_MM
        time_series_filt = signal.lfilter(self.B, self.A, time_series_unwrapped, axis=0)[
            self._IIR_INIT_LENGTH :
        ]

        # Filter amplitudes and determine at what distance to plot time series.
        self.ampl_lp_filt = self._AMPL_LP_COEFF * self.ampl_lp_filt + (
            1 - self._AMPL_LP_COEFF
        ) * np.abs(result.frame)
        distance_to_plot = np.argmax(self.ampl_lp_filt)
        distance_to_plot_m = (
            float(self.start_point + distance_to_plot * self.step_length)
            * APPROX_BASE_STEP_LENGTH_M
        )

        # Calculate psd.
        freqs, psd = signal.welch(
            x=time_series_filt,
            fs=self.frame_rate,
            window="hann",
            nperseg=self.window_length,
            nfft=self.time_series_len * self._OVER_SAMPLING_FACTOR,
            axis=0,
            average="mean",
        )

        # Weigh psd with filtered amplitude and psd over distances.
        psd = np.mean(psd * self.ampl_lp_filt, axis=1)

        if not self.has_init:
            self.lp_psd = psd
            self.ampl_lp_filt = np.abs(result.frame)
            self.has_init = True

        assert self.lp_psd is not None
        self.lp_psd = self.lp_psd * self.lp_coeff + psd * (1 - self.lp_coeff)

        idx_to_analyze = np.where(freqs < self.max_freq)[0]
        freqs_to_analyze = freqs[idx_to_analyze]
        psd_to_analyze = self.lp_psd[idx_to_analyze]
        fft_peak_loc_idx = np.argmax(psd_to_analyze)

        # Make sure max value is not first or last element in psd.
        if (fft_peak_loc_idx != 0) & (fft_peak_loc_idx != (freqs_to_analyze.shape[0] - 1)):
            fft_interpolated_freq = self.interpolate_peaks(
                psd_to_analyze[fft_peak_loc_idx - 1 : fft_peak_loc_idx + 2],
                freqs_to_analyze[fft_peak_loc_idx - 1 : fft_peak_loc_idx + 2],
            )
            breathing_rate = fft_interpolated_freq * self._SECONDS_PER_MINUTE

            return ProcessorResult(
                time_series=time_series_filt[:, distance_to_plot],
                distance_to_analyze_m=distance_to_plot_m,
                lp_psd=psd_to_analyze,
                freqs=freqs_to_analyze,
                breathing_rate=breathing_rate,
                fft_peak_location=fft_interpolated_freq,
            )

        else:
            return ProcessorResult(
                time_series=time_series_filt[:, distance_to_plot],
                distance_to_analyze_m=distance_to_plot_m,
                freqs=freqs_to_analyze,
            )

    @staticmethod
    def interpolate_peaks(ampls: npt.NDArray[np.float_], freqs: npt.NDArray[np.float_]) -> float:
        x = freqs
        y = ampls
        a = (x[0] * (y[2] - y[1]) + x[1] * (y[0] - y[2]) + x[2] * (y[1] - y[0])) / (
            (x[0] - x[1]) * (x[0] - x[2]) * (x[1] - x[2])
        )
        b = (y[1] - y[0]) / (x[1] - x[0]) - a * (x[0] + x[1])
        return float(-b / (2 * a))

    def update_config(self, config: ProcessorConfig) -> None:
        ...


def get_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        profile=a121.Profile.PROFILE_3,
        hwaas=16,
        num_points=10,
        step_length=24,
        start_point=150,
        receiver_gain=12,
        sweeps_per_frame=1,
        frame_rate=50,
    )
