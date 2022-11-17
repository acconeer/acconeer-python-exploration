# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import APPROX_BASE_STEP_LENGTH_M, AlgoConfigBase, ProcessorBase


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoConfigBase):
    time_series_length: int = attrs.field(default=512)
    """Length of time series."""

    lp_coeff: float = attrs.field(default=0.75)
    """Specify filter coefficient of exponential filter."""


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorResult:
    time_series: npt.NDArray[np.float_]
    lp_z_abs_db: npt.NDArray[np.float_]
    freqs: npt.NDArray[np.float_]
    max_amplitude: float


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:

        if sensor_config.sweep_rate is None:
            raise ValueError("Sweep rate must be set.")

        if sensor_config.continuous_sweep_mode is False:
            raise ValueError("Continuous sweep mode must be enabled.")

        if sensor_config.double_buffering is False:
            raise ValueError("Double buffer mode must be enabled.")

        if sensor_config.num_points != 1:
            raise ValueError("Number of points must be set to 1.")

        self.spf = sensor_config.sweeps_per_frame
        self.lp_coeffs = processor_config.lp_coeff

        self.time_series = np.zeros(shape=processor_config.time_series_length)
        self.freq = np.fft.rfftfreq(
            processor_config.time_series_length, 1 / sensor_config.sweep_rate
        )[1:]
        self.lp_z_abs_db = np.zeros_like(self.freq)

    def process(self, result: a121.Result) -> ProcessorResult:

        new_data_segment = np.angle(result.frame.squeeze(axis=1))

        self.time_series = np.roll(self.time_series, -self.spf)
        self.time_series[-self.spf :] = new_data_segment
        self.time_series = np.unwrap(self.time_series)

        z_abs = np.abs(np.fft.rfft(self.time_series - np.mean(self.time_series)))[1:]
        z_abs_db = 20 * np.log10(z_abs)
        self.lp_z_abs_db = self.lp_z_abs_db * self.lp_coeffs + z_abs_db * (1 - self.lp_coeffs)

        presented_time_series = (
            (self.time_series - np.mean(self.time_series)) * APPROX_BASE_STEP_LENGTH_M * 1000
        )

        max_amplitude = float(np.max(np.abs(result.frame)))

        return ProcessorResult(
            time_series=presented_time_series,
            lp_z_abs_db=self.lp_z_abs_db,
            freqs=self.freq,
            max_amplitude=max_amplitude,
        )

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
