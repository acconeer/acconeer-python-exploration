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
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase, ProcessorBase
from acconeer.exptool.a121.algo._utils import get_distances_m


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    intra_enable: bool = attrs.field(default=True)
    inter_enable: bool = attrs.field(default=True)
    intra_detection_threshold: float = attrs.field(default=1.3)
    inter_detection_threshold: float = attrs.field(default=1)
    inter_phase_boost: bool = attrs.field(default=False)
    phase_adaptivity_tc: float = attrs.field(default=5)
    inter_frame_presence_timeout: Optional[int] = attrs.field(default=None)
    inter_frame_fast_cutoff: float = attrs.field(default=20.0)
    inter_frame_slow_cutoff: float = attrs.field(default=0.2)
    inter_frame_deviation_time_const: float = attrs.field(default=0.5)
    inter_output_time_const: float = attrs.field(default=5)
    intra_frame_time_const: float = attrs.field(default=0.15)
    intra_output_time_const: float = attrs.field(default=0.5)
    history_length_s: int = attrs.field(default=5)

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if len(config.sensor_config.subsweeps) > 1:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "subsweeps",
                    "Multiple subsweeps are not supported",
                )
            )

        if config.sensor_config.frame_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "frame_rate",
                    "Must be set",
                )
            )

        if config.sensor_config.sweeps_per_frame <= Processor.NOISE_ESTIMATION_DIFF_ORDER:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "sweeps_per_frame",
                    f"Must be greater than {Processor.NOISE_ESTIMATION_DIFF_ORDER}",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext:
    estimated_frame_rate: Optional[float] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    frame: npt.NDArray[np.complex_] = attrs.field()
    abs_mean_sweep: npt.NDArray[np.float_] = attrs.field()
    fast_lp_mean_sweep: npt.NDArray[np.float_] = attrs.field()
    slow_lp_mean_sweep: npt.NDArray[np.float_] = attrs.field()
    lp_noise: npt.NDArray[np.float_] = attrs.field()
    inter: npt.NDArray[np.float_] = attrs.field()
    intra: npt.NDArray[np.float_] = attrs.field()
    presence_distance_index: int = attrs.field()
    inter_presence_history: npt.NDArray[np.float_] = attrs.field()
    intra_presence_history: npt.NDArray[np.float_] = attrs.field()


@attrs.frozen(kw_only=True)
class ProcessorResult:
    intra_presence_score: float = attrs.field()
    inter_presence_score: float = attrs.field()
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
    MAX_AMPLITUDE_WEIGHT = 15
    NOISE_ESTIMATION_DIFF_ORDER = 3

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_index: Optional[int] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        if subsweep_index is None:
            subsweep_index = 0

        if context is None:
            context = ProcessorContext()

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.subsweep_index = subsweep_index

        self.processor_config.validate(self.sensor_config)

        # Should never happen, checked in validate
        assert self.sensor_config.frame_rate is not None

        self.sweeps_per_frame = self.sensor_config.sweeps_per_frame
        self.distances, _ = get_distances_m(self.sensor_config, metadata)
        self.num_distances = self.distances.size
        if context.estimated_frame_rate is not None:
            self.f = context.estimated_frame_rate
        else:
            self.f = self.sensor_config.frame_rate

        points_per_pulse = self.ENVELOPE_FWHM_M[sensor_config.profile] / (
            self.APPROX_BASE_STEP_LENGTH_M * sensor_config.step_length
        )
        self.depth_filter_length = max(int(round(points_per_pulse)), 1)
        self.depth_filter_length = min(self.depth_filter_length, self.num_distances)

        # Fixed parameters
        self.noise_est_diff_order = self.NOISE_ESTIMATION_DIFF_ORDER
        noise_tc = 10.0

        self.noise_sf = self._tc_to_sf(noise_tc, self.f)

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        self.lp_mean_sweep_for_abs = np.zeros(self.num_distances, dtype=np.complex_)
        self.lp_mean_sweep_for_phase = np.zeros(self.num_distances, dtype=np.complex_)
        self.mean_sweep_tc = self.processor_config.phase_adaptivity_tc
        self.mean_sweep_sf = self._tc_to_sf(self.mean_sweep_tc, self.f)
        self.lp_phase_shift = np.zeros(self.num_distances)
        self.inter_phase_boost = self.processor_config.inter_phase_boost

        self.inter_frame_presence_timeout = processor_config.inter_frame_presence_timeout
        self.previous_presence_score = 0
        self.negative_count = 0

        self.fast_lp_mean_sweep = np.zeros(self.num_distances)
        self.slow_lp_mean_sweep = np.zeros(self.num_distances)
        self.lp_inter_dev = np.zeros(self.num_distances)
        self.lp_intra_dev = np.zeros(self.num_distances)
        self.lp_noise = np.zeros(self.num_distances)

        self.intra_presence_score = 0
        self.inter_presence_score = 0
        self.presence_distance_index = 0
        self.presence_distance = 0

        history_length_n = int(round(self.f * processor_config.history_length_s))
        self.intra_presence_history = np.zeros(history_length_n)
        self.inter_presence_history = np.zeros(history_length_n)
        self.update_index = 0

        self.intra_enable = processor_config.intra_enable
        self.intra_threshold = processor_config.intra_detection_threshold

        self.inter_enable = processor_config.inter_enable
        self.inter_threshold = processor_config.inter_detection_threshold

        self.update_config(processor_config)

    def update_config(self, processor_config: ProcessorConfig) -> None:
        self.intra_enable = processor_config.intra_enable
        self.inter_enable = processor_config.inter_enable
        self.intra_threshold = processor_config.intra_detection_threshold
        self.inter_threshold = processor_config.inter_detection_threshold

        self.fast_sf = self._cutoff_to_sf(processor_config.inter_frame_fast_cutoff, self.f)
        self.slow_sf = self._cutoff_to_sf(processor_config.inter_frame_slow_cutoff, self.f)
        self.inter_dev_sf = self._tc_to_sf(
            processor_config.inter_frame_deviation_time_const, self.f
        )
        self.intra_sf = self._tc_to_sf(processor_config.intra_frame_time_const, self.f)
        self.intra_output_sf = self._tc_to_sf(processor_config.intra_output_time_const, self.f)
        self.inter_output_sf = self._tc_to_sf(processor_config.inter_output_time_const, self.f)

        self.inter_frame_presence_timeout = self.processor_config.inter_frame_presence_timeout
        self.inter_phase_boost = self.processor_config.inter_phase_boost
        self.mean_sweep_tc = processor_config.phase_adaptivity_tc
        self.mean_sweep_sf = self._tc_to_sf(self.mean_sweep_tc, self.f)

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

        return np.correlate(a, b, mode="same")

    @staticmethod
    def _calculate_phase_shift(a: npt.NDArray, b: npt.NDArray) -> npt.NDArray[np.float_]:
        phase_a = np.angle(a)
        phase_b = np.angle(b)
        phases_unwrapped = np.unwrap([phase_a, phase_b], axis=0)
        phase_shift = np.abs(phases_unwrapped[0, :] - phases_unwrapped[1, :])

        return phase_shift  # type: ignore[no-any-return]

    def _calculate_phase_and_amp_weight(self, mean_sweep: npt.NDArray) -> np.float_:
        """
        Calculation of a weight factor based on phase shift and amplitude.
        The phase shift between the mean sweep and a lp-filtered mean sweep is
        calculated to amplify slow motions.
        The amplitude of the mean sweep is multiplied with the phase shift to reduce
        noise amplification.
        Before multiplication with the phase shift, the amplitude is truncated to reduce
        side effects from very strong reflective objects.
        """

        phase_shift = self._calculate_phase_shift(self.lp_mean_sweep_for_phase, mean_sweep)
        sf = self._dynamic_sf(self.inter_dev_sf, self.update_index)
        self.lp_phase_shift = sf * self.lp_phase_shift + (1.0 - sf) * phase_shift

        self.lp_mean_sweep_for_abs = sf * self.lp_mean_sweep_for_abs + (1.0 - sf) * mean_sweep
        abs_lp_mean_sweep = np.abs(self.lp_mean_sweep_for_abs)

        norm_abs_mean_sweep = np.divide(
            abs_lp_mean_sweep,
            self.lp_noise,
            out=np.zeros_like(abs_lp_mean_sweep),
            where=(self.lp_noise > 1.0),
        )

        norm_abs_mean_sweep *= np.sqrt(self.sweeps_per_frame)

        # Truncate if amplitude is too strong
        norm_abs_mean_sweep = np.minimum(
            norm_abs_mean_sweep, np.ones(norm_abs_mean_sweep.shape[0]) * self.MAX_AMPLITUDE_WEIGHT
        )

        return self.lp_phase_shift * norm_abs_mean_sweep  # type: ignore[no-any-return]

    def _inter_presence_score_scaling(self) -> None:
        """
        Scaling of self.inter_presence_score for faster decline when loosing detection.
        Start exponential scaling after self.inter_frame_presence_timeout seconds.
        """

        if self.inter_frame_presence_timeout is None:
            raise ValueError("inter_frame_presence_timeout must be set")

        scaling_factor = np.exp(
            np.maximum(self.negative_count - self.inter_frame_presence_timeout * self.f, 0)
            / (self.inter_frame_presence_timeout * self.f)
        )
        self.inter_presence_score /= scaling_factor

    def _mean_sweep_sf_scaling(self) -> None:
        """
        Scaling of self.mean_sweep_sf for faster adaptation to the environment when
        loosing detection.
        Start exponential scaling after self.inter_frame_presence_timeout seconds.
        """

        if self.inter_frame_presence_timeout is None:
            raise ValueError("inter_frame_presence_timeout must be set")

        scaling_factor = np.exp(
            np.maximum(self.negative_count - self.inter_frame_presence_timeout * self.f, 0)
            * self.mean_sweep_tc
            / self.inter_frame_presence_timeout
        )
        self.mean_sweep_sf = self._tc_to_sf(self.mean_sweep_tc / scaling_factor, self.f)

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

        intra_presence_distance_index = int(np.argmax(intra))
        intra_presence_distance = self.distances[intra_presence_distance_index]

        self.intra_presence_score = (
            self.intra_output_sf * self.intra_presence_score
            + (1.0 - self.intra_output_sf) * intra[intra_presence_distance_index]
        )

        # Inter-frame part

        mean_sweep = frame.mean(axis=0)
        abs_mean_sweep = np.abs(mean_sweep)

        sf = self._dynamic_sf(self.fast_sf, self.update_index)
        self.fast_lp_mean_sweep = sf * self.fast_lp_mean_sweep + (1.0 - sf) * abs_mean_sweep

        sf = self._dynamic_sf(self.slow_sf, self.update_index)
        self.slow_lp_mean_sweep = sf * self.slow_lp_mean_sweep + (1.0 - sf) * abs_mean_sweep

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

        # Phase and amplitude weighting of inter-frame part

        if self.inter_phase_boost:
            if self.update_index == 0:
                self.lp_mean_sweep_for_phase = mean_sweep

            phase_and_amp_weight = self._calculate_phase_and_amp_weight(mean_sweep)

            inter = inter * phase_and_amp_weight

            sf = self._dynamic_sf(self.mean_sweep_sf, self.update_index)
            self.lp_mean_sweep_for_phase = (
                sf * self.lp_mean_sweep_for_phase + (1.0 - sf) * mean_sweep
            )

        inter_presence_distance_index = int(np.argmax(inter))
        inter_presence_distance = self.distances[inter_presence_distance_index]

        sf = self._dynamic_sf(self.inter_output_sf, self.update_index)
        self.inter_presence_score = (
            sf * self.inter_presence_score + (1.0 - sf) * inter[inter_presence_distance_index]
        )

        # Inter-frame presence timeout

        if self.inter_frame_presence_timeout:
            delta = self.inter_presence_score - self.previous_presence_score

            if delta < 0:
                self.negative_count += 1
            else:
                self.negative_count = 0

            self._inter_presence_score_scaling()
            self._mean_sweep_sf_scaling()

            self.previous_presence_score = self.inter_presence_score

        # Presence distance - intra presence distance is prioritized due to faster reaction time

        if self.intra_presence_score > self.intra_threshold and self.intra_enable:
            presence_detected = True
            self.presence_distance_index = intra_presence_distance_index
            self.presence_distance = intra_presence_distance
        elif self.inter_presence_score > self.inter_threshold and self.inter_enable:
            presence_detected = True
            self.presence_distance_index = inter_presence_distance_index
            self.presence_distance = inter_presence_distance
        else:
            presence_detected = False
            self.presence_distance = 0

        # TODO: self.presence_history will be removed in the future
        self.intra_presence_history = np.roll(self.intra_presence_history, -1)
        self.intra_presence_history[-1] = self.intra_presence_score

        self.inter_presence_history = np.roll(self.inter_presence_history, -1)
        self.inter_presence_history[-1] = self.inter_presence_score

        self.update_index += 1

        extra_result = ProcessorExtraResult(
            frame=frame,
            abs_mean_sweep=abs_mean_sweep,
            fast_lp_mean_sweep=self.fast_lp_mean_sweep,
            slow_lp_mean_sweep=self.slow_lp_mean_sweep,
            lp_noise=self.lp_noise,
            inter=inter,
            intra=intra,
            presence_distance_index=self.presence_distance_index,
            intra_presence_history=self.intra_presence_history,
            inter_presence_history=self.inter_presence_history,
        )

        return ProcessorResult(
            intra_presence_score=self.intra_presence_score,
            inter_presence_score=self.inter_presence_score,
            presence_detected=presence_detected,
            presence_distance=self.presence_distance,
            extra_result=extra_result,
        )
