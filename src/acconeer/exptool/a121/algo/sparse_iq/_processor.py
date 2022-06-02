from __future__ import annotations

from enum import Enum

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import Processor


class AmplitudeMethod(Enum):
    COHERENT = "Coherent"
    NONCOHERENT = "Noncoherent"
    FFT_MAX = "FFT max"


@attrs.frozen(kw_only=True)
class SparseIQProcessorConfig:
    amplitude_method: AmplitudeMethod = attrs.field(default=AmplitudeMethod.COHERENT)


@attrs.frozen(kw_only=True)
class SparseIQProcessorResult:
    frame: npt.NDArray[np.complex_]
    distance_velocity_map: npt.NDArray[np.float_]
    amplitudes: npt.NDArray[np.float_]
    phases: npt.NDArray[np.float_]


class SparseIQProcessor(Processor[SparseIQProcessorConfig, SparseIQProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: SparseIQProcessorConfig,
    ) -> None:
        self.processor_config = processor_config
        spf = sensor_config.sweeps_per_frame
        self.window = np.hanning(spf)[:, None]
        self.window /= np.sum(self.window)

    def process(self, result: a121.Result) -> SparseIQProcessorResult:
        frame = result.frame

        z_ft = np.fft.fftshift(np.fft.fft(frame * self.window, axis=0), axes=(0,))
        abs_z_ft = np.abs(z_ft)

        amplitude_method = self.processor_config.amplitude_method
        if amplitude_method == AmplitudeMethod.COHERENT:
            ampls = np.abs(frame.mean(axis=0))
        elif amplitude_method == AmplitudeMethod.NONCOHERENT:
            ampls = np.abs(frame).mean(axis=0)
        elif amplitude_method == AmplitudeMethod.FFT_MAX:
            ampls = abs_z_ft.mean(axis=0)
        else:
            raise RuntimeError(f"Unknown AmplitudeMethod: {amplitude_method}")

        phases = np.angle(frame.mean(axis=0))

        return SparseIQProcessorResult(
            frame=frame,
            distance_velocity_map=abs_z_ft,
            amplitudes=ampls,
            phases=phases,
        )

    def update_config(self, config: SparseIQProcessorConfig) -> None:
        self.processor_config = config
