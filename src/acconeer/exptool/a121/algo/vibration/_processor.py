# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    AlgoProcessorConfigBase,
    ProcessorBase,
)


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    time_series_length: int = attrs.field(default=512)
    """Length of time series."""

    lp_coeff: float = attrs.field(default=0.75)
    """Specify filter coefficient of exponential filter."""

    sensitivity: float = attrs.field(default=10.0)
    """Specify threshold sensitivity."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

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

        if not config.sensor_config.double_buffering:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "double_buffering",
                    "Must be enabled",
                )
            )

        if not config.sensor_config.continuous_sweep_mode:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "continuous_sweep_mode",
                    "Must be enabled",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorResult:
    time_series: npt.NDArray[np.float_]
    lp_z_abs_db: npt.NDArray[np.float_]
    freqs: npt.NDArray[np.float_]
    max_amplitude: float
    max_psd_ampl: float
    max_psd_ampl_freq: float


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):

    _OVER_SAMPLING_FACTOR = 2
    _WINDOW_BASE_LENGTH = 10
    _HALF_GUARD_BASE_LENGTH = 5

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

        # Should never happen, checked in validate
        assert sensor_config.sweep_rate is not None

        self.spf = sensor_config.sweeps_per_frame
        self.lp_coeffs = processor_config.lp_coeff
        self.sensitivity = processor_config.sensitivity
        self.time_series_length = processor_config.time_series_length

        self.time_series = np.zeros(shape=processor_config.time_series_length)
        self.freq = np.fft.rfftfreq(
            self._OVER_SAMPLING_FACTOR * processor_config.time_series_length,
            1 / sensor_config.sweep_rate,
        )[1:]
        self.lp_z_abs_db = np.zeros_like(self.freq)
        self.window_length = self._WINDOW_BASE_LENGTH * self._OVER_SAMPLING_FACTOR
        self.half_guard_length = self._HALF_GUARD_BASE_LENGTH * self._OVER_SAMPLING_FACTOR

    def process(self, result: a121.Result) -> ProcessorResult:

        new_data_segment = np.angle(result.frame.squeeze(axis=1))

        self.time_series = np.roll(self.time_series, -self.spf)
        self.time_series[-self.spf :] = new_data_segment
        self.time_series = np.unwrap(self.time_series)

        z_abs = np.abs(
            np.fft.rfft(
                self.time_series - np.mean(self.time_series),
                n=self.time_series_length * self._OVER_SAMPLING_FACTOR,
            )
        )[1:]
        z_abs_db = 20 * np.log10(z_abs)
        self.lp_z_abs_db = self.lp_z_abs_db * self.lp_coeffs + z_abs_db * (1 - self.lp_coeffs)

        presented_time_series = (
            (self.time_series - np.mean(self.time_series)) * APPROX_BASE_STEP_LENGTH_M * 1000
        )

        max_amplitude = float(np.max(np.abs(result.frame)))

        threshold = self._calculate_cfar_threshold(
            self.lp_z_abs_db, self.sensitivity, self.window_length, self.half_guard_length
        )
        # Find index of values over threshold
        idx_over_threshold = np.where(threshold < self.lp_z_abs_db)[0]
        if idx_over_threshold.shape[0] != 0:
            psd_ampls_over_threshold = self.lp_z_abs_db[idx_over_threshold]
            max_psd_ampl = np.max(psd_ampls_over_threshold)
            max_psd_ampl_freq = self.freq[idx_over_threshold[np.argmax(psd_ampls_over_threshold)]]
        else:
            max_psd_ampl = None
            max_psd_ampl_freq = None

        return ProcessorResult(
            time_series=presented_time_series,
            lp_z_abs_db=self.lp_z_abs_db,
            freqs=self.freq,
            max_amplitude=max_amplitude,
            max_psd_ampl=max_psd_ampl,
            max_psd_ampl_freq=max_psd_ampl_freq,
        )

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

    def update_config(self, config: ProcessorConfig) -> None:
        ...


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
