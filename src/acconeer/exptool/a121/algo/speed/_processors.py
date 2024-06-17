# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

from typing import Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt
from scipy.signal import welch

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import PERCEIVED_WAVELENGTH, AlgoProcessorConfigBase, ProcessorBase


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    threshold: Optional[float] = attrs.field(default=10.0)

    num_segments: int = attrs.field(default=3)

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    velocities: npt.NDArray[np.float64]
    psd: npt.NDArray[np.float64]
    est_peaks: npt.NDArray[np.float64]
    actual_thresholds: npt.NDArray[np.float64]


@attrs.frozen(kw_only=True)
class ProcessorResult:
    extra_result: ProcessorExtraResult
    speed_per_depth: npt.NDArray[np.float64]

    @property
    def max_speed(self) -> np.float64:
        return max(np.min(self.speed_per_depth), np.max(self.speed_per_depth), key=np.abs)


class Processor(ProcessorBase[ProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
    ) -> None:
        self.threshold = processor_config.threshold
        self.num_points = sensor_config.num_points
        self.num_segments = processor_config.num_segments
        self.segment_length = sensor_config.sweeps_per_frame // self.num_segments

        if self.segment_length < 2:
            self.segment_length = 2

        assert sensor_config.sweep_rate is not None
        assert sensor_config.continuous_sweep_mode is not None

        self.sweep_rate = sensor_config.sweep_rate

    def get_welch(
        self, sweep: npt.NDArray[np.complex128]
    ) -> Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        freqs, psd = welch(
            sweep,
            fs=self.sweep_rate,
            window="hann",
            nperseg=self.segment_length,
            noverlap=0,
            average="mean",
            axis=0,
            return_onesided=False,
        )
        psd = np.fft.fftshift(psd, axes=0)
        freqs = np.fft.fftshift(freqs, axes=0)
        return freqs, psd

    def interpolate_peak(self, freqs: npt.NDArray[np.float64], peak_ind: int) -> float:
        # we assume indices to be -1,0,1 and take a inverse based on that.

        freqs = np.squeeze(freqs)
        if peak_ind == len(freqs) - 1 or peak_ind == 0:
            return peak_ind
        y1 = freqs[peak_ind - 1]
        y2 = freqs[peak_ind]
        y3 = freqs[peak_ind + 1]
        ys = np.array([y1, y2, y3])
        # Inverse of [[1,-1,1],[0,0,1],[1,1,1]]
        # fast_mat = np.array([[0.5, -1.0, 0.5], [-0.5, 0.0, 0.5], [0.0,1.0,0.0]])
        fast_mat = np.array([[0.5, -1.0, 0.5], [-0.5, 0.0, 0.5]])
        coeffs = np.dot(fast_mat, ys)
        max_ind = -coeffs[1] / (2 * coeffs[0])
        return float(peak_ind + max_ind)

    def interpolate_linear(self, speeds: npt.NDArray[np.float64], peak: float) -> float:
        p1 = int(np.floor(peak))
        p2 = int(np.ceil(peak))
        diff = speeds[p2] - speeds[p1]
        return float(speeds[p1] + diff * (peak - p1))

    def process(self, result: a121.Result) -> ProcessorResult:
        freqs, psd = self.get_welch(result.frame)

        speeds = freqs * PERCEIVED_WAVELENGTH

        peak_inds = np.argmax(psd, axis=0)

        speed_estimates = np.zeros(self.num_points)
        real_peaks = np.zeros(self.num_points)
        actual_thresholds = np.zeros(self.num_points)

        for i, peak_ind in enumerate(peak_inds):
            median = np.median(psd[:, i])
            norm_vals = psd[:, i] / median
            actual_thresholds[i] = median * self.threshold

            if norm_vals[peak_ind] > self.threshold:
                real_peak = self.interpolate_peak(norm_vals, peak_ind)
                real_speed = self.interpolate_linear(speeds, real_peak)
                real_peaks[i] = real_peak
                speed_estimates[i] = real_speed
            else:
                speed_estimates[i] = 0.0
                real_peaks[i] = 0.0

        extra_result = ProcessorExtraResult(
            velocities=speeds,
            psd=psd,
            est_peaks=real_peaks,
            actual_thresholds=actual_thresholds,
        )

        processor_result = ProcessorResult(
            extra_result=extra_result, speed_per_depth=speed_estimates
        )

        return processor_result
