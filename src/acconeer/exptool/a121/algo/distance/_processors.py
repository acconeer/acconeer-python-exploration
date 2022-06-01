from __future__ import annotations

import enum
from typing import Any, Optional

import attrs
import numpy as np
import numpy.typing as npt
from scipy.signal import butter, filtfilt

from acconeer.exptool import a121
from acconeer.exptool.a121 import algo


class ProcessorMode(enum.Enum):
    DISTANCE_ESTIMATION = enum.auto()
    LEAKAGE_CALIBRATION = enum.auto()
    RECORDED_THRESHOLD_CALIBRATION = enum.auto()


class ThresholdMethod(enum.Enum):
    CFAR = enum.auto()
    FIXED = enum.auto()
    RECORDED = enum.auto()


@attrs.frozen(kw_only=True)
class DistanceProcessorConfig:
    processor_mode: ProcessorMode = attrs.field(default=ProcessorMode.DISTANCE_ESTIMATION)
    threshold_method: ThresholdMethod = attrs.field(default=ThresholdMethod.CFAR)
    sc_bg_num_std_dev: float = attrs.field(default=3.0)


@attrs.frozen(kw_only=True)
class DistanceProcessorContext:
    pass  # e.g. calibration, background measurement


@attrs.frozen(kw_only=True)
class DistanceProcessorExtraResult:
    abs_sweep: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class DistanceProcessorResult:
    distance: Optional[float] = attrs.field(default=None)
    threshold: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    extra: DistanceProcessorExtraResult = attrs.field(factory=DistanceProcessorExtraResult)


class DistanceProcessor(algo.Processor[DistanceProcessorConfig, DistanceProcessorResult]):
    """Distance processor

    For all used subsweeps, the ``profile`` and ``step_length`` must be the same.

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    :param subsweep_indexes:
        The subsweep indexes to be processed. If ``None``, all subsweeps will be used.
    :param context: Context
    """

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: DistanceProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[DistanceProcessorContext] = None,
    ) -> None:
        if subsweep_indexes is None:
            subsweep_indexes = list(range(sensor_config.num_subsweeps))

        subsweep_configs = self._get_subsweep_configs(sensor_config, subsweep_indexes)

        self._validate(subsweep_configs)

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.subsweep_indexes = subsweep_indexes
        self.context = context

        self.profile = self._get_profile(subsweep_configs)
        self.step_length = self._get_step_length(subsweep_configs)
        self.start_point = self._get_start_point(subsweep_configs)
        self.num_points = self._get_num_points(subsweep_configs)

        (self.b, self.a) = self._get_distance_filter_coeffs(self.profile, self.step_length)

        self.processor_mode = processor_config.processor_mode
        self.threshold_method = processor_config.threshold_method

        if self.processor_mode == ProcessorMode.DISTANCE_ESTIMATION:
            pass
        elif self.processor_mode == ProcessorMode.LEAKAGE_CALIBRATION:
            pass
        elif self.processor_mode == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION:
            self._init_recorded_threshold_calibration()
        else:
            raise RuntimeError

    @classmethod
    def _get_subsweep_configs(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> list[a121.SubsweepConfig]:
        return [sensor_config.subsweeps[i] for i in subsweep_indexes]

    @classmethod
    def _get_profile(cls, subsweep_configs: list[a121.SubsweepConfig]) -> a121.Profile:
        profiles = {c.profile for c in subsweep_configs}

        if len(profiles) > 1:
            raise ValueError

        (profile,) = profiles
        return profile

    @classmethod
    def _get_step_length(cls, subsweep_configs: list[a121.SubsweepConfig]) -> int:
        step_lengths = {c.step_length for c in subsweep_configs}

        if len(step_lengths) > 1:
            raise ValueError

        (step_length,) = step_lengths
        return step_length

    @classmethod
    def _get_start_point(cls, subsweep_configs: list[a121.SubsweepConfig]) -> int:
        return subsweep_configs[0].start_point

    @classmethod
    def _get_num_points(cls, subsweep_configs: list[a121.SubsweepConfig]) -> int:
        return sum(c.num_points for c in subsweep_configs)

    @classmethod
    def _validate(cls, subsweep_configs: list[a121.SubsweepConfig]) -> None:
        cls._validate_range(subsweep_configs)

        for c in subsweep_configs:
            if not c.phase_enhancement:
                raise ValueError

    @classmethod
    def _validate_range(cls, subsweep_configs: list[a121.SubsweepConfig]) -> None:
        step_length = cls._get_step_length(subsweep_configs)

        next_expected_start_point = None

        for c in subsweep_configs:
            if next_expected_start_point is not None:
                if c.start_point != next_expected_start_point:
                    raise ValueError

            next_expected_start_point = c.start_point + c.num_points * step_length

    def process(self, result: a121.Result) -> DistanceProcessorResult:
        subframes = [result.subframes[i] for i in self.subsweep_indexes]
        frame = np.concatenate(subframes, axis=1)
        sweep = frame.mean(axis=0)
        filtered_sweep = filtfilt(self.b, self.a, sweep)
        abs_sweep = np.abs(filtered_sweep)

        if self.processor_mode == ProcessorMode.DISTANCE_ESTIMATION:
            pass
        elif self.processor_mode == ProcessorMode.LEAKAGE_CALIBRATION:
            pass
        elif self.processor_mode == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION:
            return self._process_recorded_threshold_calibration(abs_sweep)

        raise RuntimeError

    def _init_recorded_threshold_calibration(self) -> None:
        self.bg_sc_mean = np.zeros(self.num_points)
        self.bg_sc_sum_squared_bg_sweeps = np.zeros(self.num_points)
        self.sc_bg_num_sweeps = 1.0
        self.sc_bg_num_std_dev = self.processor_config.sc_bg_num_std_dev

    def _process_recorded_threshold_calibration(
        self, sweep: npt.NDArray[np.float_]
    ) -> DistanceProcessorResult:
        min_num_sweeps_in_valid_threshold = 2

        self.bg_sc_mean += sweep
        self.bg_sc_sum_squared_bg_sweeps += np.square(sweep)
        mean_sweep = self.bg_sc_mean / self.sc_bg_num_sweeps
        mean_square = self.bg_sc_sum_squared_bg_sweeps / self.sc_bg_num_sweeps
        square_mean = np.square(mean_sweep)
        sc_bg_sweep_std = np.sqrt(
            np.abs(mean_square - square_mean) * self.sc_bg_num_sweeps / (self.sc_bg_num_sweeps - 1)
        )
        threshold = mean_sweep + self.sc_bg_num_std_dev * sc_bg_sweep_std
        if self.sc_bg_num_sweeps < min_num_sweeps_in_valid_threshold:
            threshold = None
        self.sc_bg_num_sweeps += 1

        return DistanceProcessorResult(threshold=threshold)

    def update_config(self, config: DistanceProcessorConfig) -> None:
        ...

    @staticmethod
    def _get_distance_filter_coeffs(profile: a121.Profile, step_length: int) -> Any:
        envelope_width_mm = {
            a121.Profile.PROFILE_1: 40,
            a121.Profile.PROFILE_2: 70,
            a121.Profile.PROFILE_3: 140,
            a121.Profile.PROFILE_4: 190,
            a121.Profile.PROFILE_5: 320,
        }
        wnc = 2.5 * step_length / envelope_width_mm[profile]
        return butter(N=2, Wn=wnc)
