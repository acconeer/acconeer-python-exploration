# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt
from numpy import cos, pi, sqrt, square
from scipy.special import binom

from acconeer.exptool import a121
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_isclose
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase, ProcessorBase
from acconeer.exptool.a121.algo._utils import get_distances_m


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    intra_enable: bool = attrs.field(default=True)
    inter_enable: bool = attrs.field(default=True)
    intra_detection_threshold: float = attrs.field(default=1.3)
    inter_detection_threshold: float = attrs.field(default=1)
    inter_frame_presence_timeout: Optional[int] = attrs.field(default=None)
    inter_frame_fast_cutoff: float = attrs.field(default=20.0)
    inter_frame_slow_cutoff: float = attrs.field(default=0.2)
    inter_frame_deviation_time_const: float = attrs.field(default=0.5)
    inter_output_time_const: float = attrs.field(default=5)
    intra_frame_time_const: float = attrs.field(default=0.15)
    intra_output_time_const: float = attrs.field(default=0.5)

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

    frame: npt.NDArray[np.complex128] = attrs.field(eq=attrs_ndarray_isclose)
    abs_mean_sweep: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    fast_lp_mean_sweep: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    slow_lp_mean_sweep: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    lp_noise: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    presence_distance_index: int = attrs.field()


@attrs.frozen(kw_only=True)
class ProcessorResult:
    intra_presence_score: float = attrs.field()
    intra: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    inter_presence_score: float = attrs.field()
    inter: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    presence_distance: float = attrs.field()
    presence_detected: bool = attrs.field()
    extra_result: ProcessorExtraResult = attrs.field()


class Processor(ProcessorBase[ProcessorResult]):
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    MAX_AMPLITUDE_WEIGHT = 5
    NOISE_ESTIMATION_DIFF_ORDER = 3

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        # Subsweep indexes contains a list of subsweep indexes for which to run the presence detector.
        # If None is supplied, use all possible.
        if subsweep_indexes is None:
            subsweep_indexes = list(range(sensor_config.num_subsweeps))
        self.subsweep_indexes = subsweep_indexes

        if context is None:
            context = ProcessorContext()

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config

        self.processor_config.validate(self.sensor_config)

        # Should never happen, checked in validate
        assert self.sensor_config.frame_rate is not None

        self.sweeps_per_frame = self.sensor_config.sweeps_per_frame
        self.distances = get_distances_m(self.sensor_config, metadata)
        self.num_distances = self.distances.size
        if context.estimated_frame_rate is not None:
            self.f = context.estimated_frame_rate
        else:
            self.f = self.sensor_config.frame_rate

        # Fixed parameters
        self.noise_est_diff_order = self.NOISE_ESTIMATION_DIFF_ORDER
        noise_tc = 10.0

        self.noise_sf = self._tc_to_sf(noise_tc, self.f)

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        self.fast_lp_mean_sweep = np.zeros(self.num_distances)
        self.slow_lp_mean_sweep = np.zeros(self.num_distances)
        self.lp_inter_dev = np.zeros(self.num_distances)
        self.lp_intra_dev = np.zeros(self.num_distances)
        self.lp_noise = np.zeros(self.num_distances)

        self.intra_presence_score = 0
        self.inter_presence_score = 0
        self.presence_distance_index = 0
        self.presence_distance = 0

        self.update_index = 0

        self.intra_enable = processor_config.intra_enable
        self.intra_threshold = processor_config.intra_detection_threshold

        self.inter_enable = processor_config.inter_enable
        self.inter_threshold = processor_config.inter_detection_threshold

        self.fast_sf = self._cutoff_to_sf(processor_config.inter_frame_fast_cutoff, self.f)
        self.slow_sf = self._cutoff_to_sf(processor_config.inter_frame_slow_cutoff, self.f)
        self.inter_dev_sf = self._tc_to_sf(
            processor_config.inter_frame_deviation_time_const, self.f
        )
        self.intra_sf = self._tc_to_sf(processor_config.intra_frame_time_const, self.f)
        self.intra_output_sf = self._tc_to_sf(processor_config.intra_output_time_const, self.f)
        self.inter_output_sf = self._tc_to_sf(processor_config.inter_output_time_const, self.f)

        self.previous_presence_score = 0
        self.negative_count = 0
        self.inter_frame_presence_timeout = self.processor_config.inter_frame_presence_timeout

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
        a: npt.NDArray[np.complex128],
        axis: Optional[int] = None,
        ddof: int = 0,
        subtract_mean: bool = True,
    ) -> npt.NDArray[np.float64]:
        if subtract_mean:
            a = a - a.mean(axis=axis, keepdims=True)

        if axis is None:
            n = a.size
        else:
            n = a.shape[axis]

        if ddof < 0:
            msg = "ddof must be greater than or equal to 0"
            raise ValueError(msg)

        if n <= ddof:
            msg = "n must be greater than ddof"
            raise ValueError(msg)

        return np.mean(np.abs(a), axis=axis) * sqrt(n / (n - ddof))  # type: ignore[no-any-return]

    def _inter_presence_score_scaling(self) -> None:
        """
        Scaling of self.inter_presence_score for faster decline when loosing detection.
        Start exponential scaling after self.inter_frame_presence_timeout seconds.
        """

        if self.inter_frame_presence_timeout is None:
            msg = "inter_frame_presence_timeout must be set"
            raise ValueError(msg)

        scaling_factor = np.exp(
            np.maximum(self.negative_count - self.inter_frame_presence_timeout * self.f, 0)
            / (self.inter_frame_presence_timeout * self.f)
        )
        self.inter_presence_score /= scaling_factor

    def process(self, result: a121.Result) -> ProcessorResult:
        range_subframes = [result.subframes[i] for i in self.subsweep_indexes]
        frame = np.concatenate(range_subframes, axis=1)

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

        intra = np.divide(
            self.lp_intra_dev,
            self.lp_noise,
            out=np.zeros(self.num_distances),
            where=(self.lp_noise > 1.0),
        )

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

        inter = np.divide(
            self.lp_inter_dev,
            self.lp_noise,
            out=np.zeros_like(self.lp_inter_dev),
            where=(self.lp_noise > 1.0),
        )

        inter *= np.sqrt(self.sweeps_per_frame)

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

        self.update_index += 1

        extra_result = ProcessorExtraResult(
            frame=frame,
            abs_mean_sweep=abs_mean_sweep,
            fast_lp_mean_sweep=self.fast_lp_mean_sweep,
            slow_lp_mean_sweep=self.slow_lp_mean_sweep,
            lp_noise=self.lp_noise,
            presence_distance_index=self.presence_distance_index,
        )

        return ProcessorResult(
            intra_presence_score=self.intra_presence_score,
            intra=intra,
            inter_presence_score=self.inter_presence_score,
            inter=inter,
            presence_detected=presence_detected,
            presence_distance=self.presence_distance,
            extra_result=extra_result,
        )


@attrs.mutable(kw_only=True)
class _ProcessorConfig_v0(AlgoProcessorConfigBase):
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

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        return []

    def migrate(self) -> ProcessorConfig:
        return ProcessorConfig(
            intra_enable=self.intra_enable,
            inter_enable=self.inter_enable,
            intra_detection_threshold=self.intra_detection_threshold,
            inter_detection_threshold=self.inter_detection_threshold,
            # phase_adaptivity_tc is removed
            inter_frame_presence_timeout=self.inter_frame_presence_timeout,
            inter_frame_fast_cutoff=self.inter_frame_fast_cutoff,
            inter_frame_slow_cutoff=self.inter_frame_slow_cutoff,
            inter_frame_deviation_time_const=self.inter_frame_deviation_time_const,
            inter_output_time_const=self.inter_output_time_const,
            intra_frame_time_const=self.intra_frame_time_const,
            intra_output_time_const=self.intra_output_time_const,
            # inter_phase_boost is removed
        )


processor_config_timeline = (
    tm.start(_ProcessorConfig_v0)
    .load(str, _ProcessorConfig_v0.from_json, fail=[TypeError])
    .load(dict, _ProcessorConfig_v0.from_dict, fail=[TypeError])
    .nop()
    .epoch(ProcessorConfig, _ProcessorConfig_v0.migrate, fail=[])
    .load(str, ProcessorConfig.from_json, fail=[TypeError])
    .load(dict, ProcessorConfig.from_dict, fail=[TypeError])
)
