from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121 import algo


class DistanceProcessorConfig:
    pass


@attrs.frozen(kw_only=True)
class DistanceProcessorContext:
    pass  # e.g. calibration, background measurement


@attrs.frozen(kw_only=True)
class DistanceProcessorResult:
    distance: Optional[float] = attrs.field()


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

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.subsweep_indexes = subsweep_indexes
        self.context = context

        self.profile = self._get_profile(sensor_config, subsweep_indexes)
        self.step_length = self._get_step_length(sensor_config, subsweep_indexes)
        self.start_point = self._get_start_point(sensor_config, subsweep_indexes)
        self.num_points = self._get_num_points(sensor_config, subsweep_indexes)

    @classmethod
    def _get_subsweep_configs(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> list[a121.SubsweepConfig]:
        return [sensor_config.subsweeps[i] for i in subsweep_indexes]

    @classmethod
    def _get_profile(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> a121.Profile:
        subsweep_configs = cls._get_subsweep_configs(sensor_config, subsweep_indexes)
        profiles = {c.profile for c in subsweep_configs}

        if len(profiles) > 1:
            raise ValueError

        (profile,) = profiles
        return profile

    @classmethod
    def _get_step_length(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> int:
        subsweep_configs = cls._get_subsweep_configs(sensor_config, subsweep_indexes)
        step_lengths = {c.step_length for c in subsweep_configs}

        if len(step_lengths) > 1:
            raise ValueError

        (step_length,) = step_lengths
        return step_length

    @classmethod
    def _get_start_point(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> int:
        subsweep_configs = cls._get_subsweep_configs(sensor_config, subsweep_indexes)
        return subsweep_configs[0].start_point

    @classmethod
    def _get_num_points(cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]) -> int:
        subsweep_configs = cls._get_subsweep_configs(sensor_config, subsweep_indexes)
        return sum(c.num_points for c in subsweep_configs)

    def process(self, result: a121.Result) -> DistanceProcessorResult:
        ...

    def update_config(self, config: DistanceProcessorConfig) -> None:
        ...
