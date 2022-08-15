# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt
from numpy import cos, pi, sqrt, square
from scipy.special import binom

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoConfigBase, ProcessorBase
from acconeer.exptool.a121.algo._utils import get_distances_m


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoConfigBase):
    detection_threshold: float = attrs.field(default=1.5)
    intra_frame_weight: float = attrs.field(default=0.6)
    inter_frame_fast_cutoff: float = attrs.field(default=20.0)
    inter_frame_slow_cutoff: float = attrs.field(default=0.2)
    inter_frame_deviation_time_const: float = attrs.field(default=0.5)
    intra_frame_time_const: float = attrs.field(default=0.15)
    output_time_const: float = attrs.field(default=0.5)
    history_length_s: int = attrs.field(default=5)


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    frame: npt.NDArray[np.complex_] = attrs.field()
    mean_sweep: npt.NDArray[np.float_] = attrs.field()
    fast_lp_mean_sweep: npt.NDArray[np.float_] = attrs.field()
    slow_lp_mean_sweep: npt.NDArray[np.float_] = attrs.field()
    lp_noise: npt.NDArray[np.float_] = attrs.field()
    inter: npt.NDArray[np.float_] = attrs.field()
    intra: npt.NDArray[np.float_] = attrs.field()
    depthwise_presence: npt.NDArray[np.float_] = attrs.field()
    presence_distance_index: int = attrs.field()
    presence_history: npt.NDArray[np.float_] = attrs.field()


@attrs.frozen(kw_only=True)
class ProcessorResult:
    presence_score: float = attrs.field()
    presence_distance: float = attrs.field()
    presence_detected: bool = attrs.field()
    extra_result: ProcessorExtraResult = attrs.field()


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    ENVELOPE_FWHM_M = {
        a121.Profile.PROFILE_1: 0.04,
        a121.Profile.PROFILE_2: 0.07,
        a121.Profile.PROFILE_3: 0.14,
        a121.Profile.PROFILE_4: 0.19,
        a121.Profile.PROFILE_5: 0.32,
    }

    APPROX_BASE_STEP_LENGTH_M = 2.5e-3

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_index: Optional[int] = None,
    ) -> None:
        if subsweep_index is None:
            if len(sensor_config.subsweeps) > 1:
                raise ValueError("Multiple subsweeps are not supported")

            subsweep_index = 0

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.subsweep_index = subsweep_index

        if self.sensor_config.frame_rate is None:
            raise ValueError("Frame rate must be set")

        self.sweeps_per_frame = self.sensor_config.sweeps_per_frame
        self.distances, _ = get_distances_m(self.sensor_config, metadata)
        self.num_distances = self.distances.size
        self.f = self.sensor_config.frame_rate

        points_per_pulse = self.ENVELOPE_FWHM_M[sensor_config.profile] / (
            self.APPROX_BASE_STEP_LENGTH_M * sensor_config.step_length
        )
        self.depth_filter_length = max(int(round(points_per_pulse)), 1)

        # Fixed parameters
        self.noise_est_diff_order = 3
        noise_tc = 10.0

        if self.sweeps_per_frame <= self.noise_est_diff_order:
            raise ValueError(
                f"Number of sweeps per frame must be greater than {self.noise_est_diff_order}"
            )

        self.noise_sf = self._tc_to_sf(noise_tc, self.f)

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        self.fast_lp_mean_sweep = np.zeros(self.num_distances)
        self.slow_lp_mean_sweep = np.zeros(self.num_distances)
        self.lp_inter_dev = np.zeros(self.num_distances)
        self.lp_intra_dev = np.zeros(self.num_distances)
        self.lp_noise = np.zeros(self.num_distances)

        self.presence_score = 0
        self.presence_distance_index = 0
        self.presence_distance = 0

        self.presence_history = np.zeros(int(round(self.f * processor_config.history_length_s)))
        self.update_index = 0

        self.threshold = processor_config.detection_threshold
        self.intra_weight = processor_config.intra_frame_weight
        self.inter_weight = 1.0 - self.intra_weight

        self.update_config(processor_config)

    def update_config(self, processor_config: ProcessorConfig) -> None:
        self.threshold = processor_config.detection_threshold
        self.intra_weight = processor_config.intra_frame_weight
        self.inter_weight = 1.0 - self.intra_weight

        self.fast_sf = self._cutoff_to_sf(processor_config.inter_frame_fast_cutoff, self.f)
        self.slow_sf = self._cutoff_to_sf(processor_config.inter_frame_slow_cutoff, self.f)
        self.inter_dev_sf = self._tc_to_sf(
            processor_config.inter_frame_deviation_time_const, self.f
        )
        self.intra_sf = self._tc_to_sf(processor_config.intra_frame_time_const, self.f)
        self.output_sf = self._tc_to_sf(processor_config.output_time_const, self.f)

    @staticmethod
    def _cutoff_to_sf(fc: float, fs: float) -> float:
        """Cutoff frequency to smoothing factor conversion"""

        if fc > 0.5 * fs:
            return 0.0

        cos_w = cos(2.0 * pi * (fc / fs))
        return 2.0 - cos_w - sqrt(square(cos_w) - 4.0 * cos_w + 3.0)  # type: ignore[no-any-return]

    @staticmethod
    def _tc_to_sf(tc: float, fs: float) -> float:
        """Time constant to smoothing factor conversion"""

        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))  # type: ignore[no-any-return]

    @staticmethod
    def _dynamic_sf(static_sf: float, update_index: int) -> float:
        return min(static_sf, 1.0 - 1.0 / (1.0 + update_index))

    @staticmethod
    def _abs_dev(
        a: npt.NDArray[np.complex_],
        axis: Optional[int] = None,
        ddof: int = 0,
        subtract_mean: bool = True,
    ) -> npt.NDArray[np.float_]:
        if subtract_mean:
            a = a - a.mean(axis=axis, keepdims=True)

        if axis is None:
            n = a.size
        else:
            n = a.shape[axis]

        if ddof < 0:
            raise ValueError("ddof must be greater than or equal to 0")

        if n <= ddof:
            raise ValueError("n must be greater than ddof")

        return np.mean(np.abs(a), axis=axis) * sqrt(n / (n - ddof))  # type: ignore[no-any-return]

    @staticmethod
    def _depth_filter(a: npt.NDArray, depth_filter_length: int) -> npt.NDArray[np.float_]:
        b = np.ones(depth_filter_length) / depth_filter_length

        if a.size >= b.size:
            return np.correlate(a, b, mode="same")
        else:
            pad_width = int(np.ceil((b.size - a.size) / 2))
            a = np.pad(a, pad_width, "constant")
            return np.correlate(a, b, mode="same")[pad_width:-pad_width]

    def process(self, result: a121.Result) -> ProcessorResult:
        frame = result.subframes[self.subsweep_index]

        # Noise estimation

        nd = self.noise_est_diff_order

        noise_diff = np.diff(frame, n=nd, axis=0)
        noise = self._abs_dev(noise_diff, axis=0, subtract_mean=False)
        noise /= self.noise_norm_factor
        sf = self._dynamic_sf(self.noise_sf, self.update_index)
        self.lp_noise = sf * self.lp_noise + (1.0 - sf) * noise

        # Intra-frame part

        sweep_dev = self._abs_dev(frame, axis=0, ddof=1)

        sf = self._dynamic_sf(self.intra_sf, self.update_index)
        self.lp_intra_dev = sf * self.lp_intra_dev + (1.0 - sf) * sweep_dev

        norm_lp_intra_dev = np.divide(
            self.lp_intra_dev,
            self.lp_noise,
            out=np.zeros(self.num_distances),
            where=(self.lp_noise > 1.0),
        )

        intra = self._depth_filter(norm_lp_intra_dev, self.depth_filter_length)

        # Inter-frame part

        mean_sweep = np.abs(frame.mean(axis=0))

        sf = self._dynamic_sf(self.fast_sf, self.update_index)
        self.fast_lp_mean_sweep = sf * self.fast_lp_mean_sweep + (1.0 - sf) * mean_sweep

        sf = self._dynamic_sf(self.slow_sf, self.update_index)
        self.slow_lp_mean_sweep = sf * self.slow_lp_mean_sweep + (1.0 - sf) * mean_sweep

        inter_dev = np.abs(self.fast_lp_mean_sweep - self.slow_lp_mean_sweep)
        sf = self._dynamic_sf(self.inter_dev_sf, self.update_index)
        self.lp_inter_dev = sf * self.lp_inter_dev + (1.0 - sf) * inter_dev

        norm_lp_dev = np.divide(
            self.lp_inter_dev,
            self.lp_noise,
            out=np.zeros_like(self.lp_inter_dev),
            where=(self.lp_noise > 1.0),
        )

        norm_lp_dev *= np.sqrt(self.sweeps_per_frame)

        inter = self._depth_filter(norm_lp_dev, self.depth_filter_length)

        # Detector output

        depthwise_presence = self.inter_weight * inter + self.intra_weight * intra

        max_depthwise_presence = np.max(depthwise_presence)

        sf = self._dynamic_sf(self.output_sf, self.update_index)
        self.presence_score = sf * self.presence_score + (1.0 - sf) * max_depthwise_presence

        presence_detected = self.presence_score > self.threshold

        # TODO: self.presence_history will be removed in the future
        self.presence_history = np.roll(self.presence_history, -1)
        self.presence_history[-1] = self.presence_score

        if max_depthwise_presence > self.threshold:
            self.presence_distance_index = int(np.argmax(depthwise_presence))
            self.presence_distance = self.distances[self.presence_distance_index]

        self.update_index += 1

        extra_result = ProcessorExtraResult(
            frame=frame,
            mean_sweep=mean_sweep,
            fast_lp_mean_sweep=self.fast_lp_mean_sweep,
            slow_lp_mean_sweep=self.slow_lp_mean_sweep,
            lp_noise=self.lp_noise,
            inter=inter * self.inter_weight,
            intra=intra * self.intra_weight,
            depthwise_presence=depthwise_presence,
            presence_distance_index=self.presence_distance_index,
            presence_history=self.presence_history,
        )

        return ProcessorResult(
            presence_score=self.presence_score,
            presence_detected=presence_detected,
            presence_distance=self.presence_distance,
            extra_result=extra_result,
        )
