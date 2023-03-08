# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import AlgoParamEnum, AlgoProcessorConfigBase, ProcessorBase


class AmplitudeMethod(AlgoParamEnum):
    COHERENT = "Coherent"
    NONCOHERENT = "Noncoherent"
    FFT_MAX = "FFT max"


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    amplitude_method: AmplitudeMethod = attrs.field(
        default=AmplitudeMethod.COHERENT, converter=AmplitudeMethod
    )

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        return []


@attrs.frozen(kw_only=True)
class SubsweepProcessorResult:
    frame: npt.NDArray[np.complex_] = attrs.field(eq=utils.attrs_ndarray_eq)
    amplitudes: npt.NDArray[np.float_] = attrs.field(eq=utils.attrs_ndarray_isclose)
    phases: npt.NDArray[np.float_] = attrs.field(eq=utils.attrs_ndarray_isclose)
    distance_velocity_map: npt.NDArray[np.float_] = attrs.field(eq=utils.attrs_ndarray_isclose)


ProcessorResult = t.List[SubsweepProcessorResult]


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
    ) -> None:
        self.processor_config = processor_config
        self.processor_config.validate(sensor_config)
        spf = sensor_config.sweeps_per_frame
        self.window = np.hanning(spf)[:, None]
        self.window /= np.sum(self.window)

    def process(self, result: a121.Result) -> ProcessorResult:
        subframes = result.subframes

        processor_result = []

        for subframe in subframes:
            z_ft = np.fft.fftshift(np.fft.fft(subframe * self.window, axis=0), axes=(0,))
            abs_z_ft = np.abs(z_ft)

            amplitude_method = self.processor_config.amplitude_method
            if amplitude_method == AmplitudeMethod.COHERENT:
                ampls = np.abs(subframe.mean(axis=0))
            elif amplitude_method == AmplitudeMethod.NONCOHERENT:
                ampls = np.abs(subframe).mean(axis=0)
            elif amplitude_method == AmplitudeMethod.FFT_MAX:
                ampls = abs_z_ft.mean(axis=0)
            else:
                raise RuntimeError(f"Unknown AmplitudeMethod: {amplitude_method}")

            phases = np.angle(subframe.mean(axis=0))

            processor_result.append(
                SubsweepProcessorResult(
                    frame=subframe, amplitudes=ampls, phases=phases, distance_velocity_map=abs_z_ft
                )
            )

        return processor_result

    def update_config(self, config: ProcessorConfig) -> None:
        self.processor_config = config


def get_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        sweeps_per_frame=32,
        num_points=40,
        step_length=8,
    )
