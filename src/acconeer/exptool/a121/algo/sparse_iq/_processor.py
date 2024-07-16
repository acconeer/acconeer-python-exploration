# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_eq, attrs_ndarray_isclose
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import (
    AlgoParamEnum,
    AlgoProcessorConfigBase,
    ExtendedProcessorBase,
)


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
    frame: npt.NDArray[np.complex128] = attrs.field(eq=attrs_ndarray_eq)
    amplitudes: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    phases: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    distance_velocity_map: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)


EntryResult = t.List[SubsweepProcessorResult]
ProcessorResult = t.List[t.Dict[int, EntryResult]]


class Processor(ExtendedProcessorBase[ProcessorResult]):
    def __init__(
        self,
        *,
        session_config: a121.SessionConfig,
        processor_config: ProcessorConfig,
    ) -> None:
        self.processor_config = processor_config
        self.processor_config.validate(session_config)

        self.windows = utils.map_over_extended_structure(
            self._get_hanning_widow, session_config.groups
        )

    @staticmethod
    def _get_hanning_widow(sensor_config: a121.SensorConfig) -> npt.NDArray[np.float64]:
        spf = sensor_config.sweeps_per_frame
        window = np.hanning(spf)[:, None]
        return window / np.sum(window)  # type: ignore[no-any-return]

    def _process_entry(
        self, result_hanning_window: t.Tuple[a121.Result, npt.NDArray[np.float64]]
    ) -> EntryResult:
        (result, hanning_window) = result_hanning_window

        entry_result = []

        for subframe in result.subframes:
            z_ft = np.fft.fftshift(np.fft.fft(subframe * hanning_window, axis=0), axes=(0,))
            abs_z_ft = np.abs(z_ft)

            amplitude_method = self.processor_config.amplitude_method
            if amplitude_method == AmplitudeMethod.COHERENT:
                ampls = np.abs(subframe.mean(axis=0))
            elif amplitude_method == AmplitudeMethod.NONCOHERENT:
                ampls = np.abs(subframe).mean(axis=0)
            elif amplitude_method == AmplitudeMethod.FFT_MAX:
                ampls = abs_z_ft.max(axis=0)
            else:
                msg = f"Unknown AmplitudeMethod: {amplitude_method}"
                raise RuntimeError(msg)

            phases = np.angle(subframe.mean(axis=0))

            entry_result.append(
                SubsweepProcessorResult(
                    frame=subframe, amplitudes=ampls, phases=phases, distance_velocity_map=abs_z_ft
                )
            )

        return entry_result

    def process(self, results: list[dict[int, a121.Result]]) -> ProcessorResult:
        return utils.map_over_extended_structure(
            self._process_entry, utils.zip_extended_structures(results, self.windows)
        )


def get_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        sweeps_per_frame=32,
        num_points=40,
        step_length=8,
    )
