from __future__ import annotations

import copy
import enum
from typing import Dict, List, Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121

from ._aggregator import Aggregator, AggregatorConfig, ProcessorSpec
from ._processors import (
    Processor,
    ProcessorConfig,
    ProcessorMode,
    ProcessorResult,
    ThresholdMethod,
)


class MeasurementType(enum.Enum):
    CLOSE_RANGE = enum.auto()
    FAR_RANGE = enum.auto()


@attrs.frozen(kw_only=True)
class SubsweepGroupPlan:
    step_length: int = attrs.field()
    breakpoints_m: list[float] = attrs.field()
    profile: a121.Profile = attrs.field()


Plan = Dict[MeasurementType, List[SubsweepGroupPlan]]


@attrs.frozen(kw_only=True)
class DetectorConfig:
    start_m: float = attrs.field()
    end_m: float = attrs.field()
    max_step_length: Optional[int] = attrs.field(default=None)
    max_profile: Optional[a121.Profile] = attrs.field(default=None)
    num_frames_in_recorded_threshold: int = attrs.field(default=10)


@attrs.frozen(kw_only=True)
class DetectorResult:
    distances: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    processor_results: list[ProcessorResult] = attrs.field()


class Detector:

    APPROX_BASE_STEP_LENGTH_M = 2.5e-3

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        detector_config: DetectorConfig,
    ) -> None:
        self.client = client
        self.sensor_id = sensor_id
        self.detector_config = detector_config

        self.started = False
        self.update_config(self.detector_config)

    def calibrate(self) -> None:
        ...

    def execute_background_measurement(self) -> None:
        if self.started:
            raise RuntimeError("Already started")

        specs = self._update_processor_mode(
            self.processor_specs, ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
        )

        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)

        aggregator = Aggregator(
            session_config=self.session_config,
            extended_metadata=extended_metadata,
            aggregator_config=AggregatorConfig(),
            specs=specs,
        )

        self.client.start_session()
        for _ in range(self.detector_config.num_frames_in_recorded_threshold):
            extended_result = self.client.get_next()
            assert isinstance(extended_result, list)
            aggregator_result = aggregator.process(extended_result=extended_result)
        self.client.stop_session()
        self.recorded_thresholds = [
            processor_result.recorded_threshold
            for processor_result in aggregator_result.processor_results
        ]

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Already started")

        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)

        self.aggregator = Aggregator(
            session_config=self.session_config,
            extended_metadata=extended_metadata,
            aggregator_config=AggregatorConfig(),
            specs=self.processor_specs,
        )

        self.client.start_session()
        self.started = True

    def get_next(self) -> DetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        extended_result = self.client.get_next()
        assert isinstance(extended_result, list)

        aggregator_result = self.aggregator.process(extended_result=extended_result)

        return DetectorResult(
            distances=aggregator_result.estimated_distances,
            processor_results=aggregator_result.processor_results,
        )

    def update_config(self, config: DetectorConfig) -> None:
        (
            self.session_config,
            self.processor_specs,
        ) = self._detector_to_session_config_and_processor_specs(
            config=config, sensor_id=self.sensor_id
        )

    def stop(self) -> None:
        if not self.started:
            raise RuntimeError("Already stopped")

        self.client.stop_session()

        self.processor = None
        self.started = False

    @classmethod
    def _detector_to_session_config_and_processor_specs(
        cls, config: DetectorConfig, sensor_id: int
    ) -> Tuple[a121.SessionConfig, list[ProcessorSpec]]:
        processor_specs = []
        groups = []
        group_index = 0

        #  TODO : Add logic for subsweep group configuration. Values below are just for
        # demonstrative purposes.
        plan = {
            MeasurementType.FAR_RANGE: [
                SubsweepGroupPlan(
                    step_length=1,
                    breakpoints_m=[config.start_m, 0.5, 1.0],
                    profile=a121.Profile.PROFILE_1,
                ),
                SubsweepGroupPlan(
                    step_length=1,
                    breakpoints_m=[1.0, config.end_m],
                    profile=a121.Profile.PROFILE_3,
                ),
            ],
        }

        if MeasurementType.FAR_RANGE in plan:
            (
                sensor_config,
                processor_specs_subsweep_indexes,
            ) = cls._far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
                plan[MeasurementType.FAR_RANGE]
            )
            groups.append({sensor_id: sensor_config})
            for subsweep_indexes in processor_specs_subsweep_indexes:
                processor_specs.append(
                    ProcessorSpec(
                        processor_config=ProcessorConfig(threshold_method=ThresholdMethod.FIXED),
                        group_index=group_index,
                        sensor_id=sensor_id,
                        subsweep_indexes=subsweep_indexes,
                    )
                )

        return (a121.SessionConfig(groups, extended=True), processor_specs)

    @classmethod
    def _far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
        cls, subsweep_group_plans: list[SubsweepGroupPlan]
    ) -> Tuple[a121.SensorConfig, list[list[int]]]:
        subsweeps = []
        processor_specs_subsweep_indexes = []
        subsweep_idx = 0
        for plan_idx, plan in enumerate(subsweep_group_plans):
            extended_breakpoints = cls._add_margins_and_convert_to_points(
                plan=plan,
                plan_idx=plan_idx,
                last_plan_idx=len(subsweep_group_plans) - 1,
            )
            subsweep_indexes = []
            for idx in range(len(extended_breakpoints) - 1):
                subsweeps.append(
                    a121.SubsweepConfig(
                        start_point=extended_breakpoints[idx],
                        num_points=extended_breakpoints[idx + 1] - extended_breakpoints[idx],
                        step_length=plan.step_length,
                        profile=plan.profile,
                        hwaas=8,
                        receiver_gain=10,
                        phase_enhancement=True,
                    )
                )
                subsweep_indexes.append(subsweep_idx)
                subsweep_idx += 1
            processor_specs_subsweep_indexes.append(subsweep_indexes)
        return (a121.SensorConfig(subsweeps=subsweeps), processor_specs_subsweep_indexes)

    @classmethod
    def _add_margins_and_convert_to_points(
        cls, plan: SubsweepGroupPlan, plan_idx: int, last_plan_idx: int
    ) -> npt.NDArray[np.int_]:
        """
        Add margin to edges of the range spanned by a subsweep group.

        A margin is added for the following two reasons(if both reasons are applicable, two margins
        are added)

        1. Add margin to edges of each subsweep group plan for distance filter initialization.
        2. Add margin to edges of neigbouring subsweep group plans to create overlap for smooth
        transition between segments(utilizing peak merging).

        Before returned, the extended range is converted from meters to points.
        """
        (margin_m, _) = Processor.distance_filter_init_margin(plan.profile, plan.step_length)
        extended_breakpoints_m = copy.copy(plan.breakpoints_m)
        if plan_idx == 0:
            extended_breakpoints_m[0] -= margin_m
            extended_breakpoints_m[-1] += 2 * margin_m
        elif plan_idx == last_plan_idx:
            extended_breakpoints_m[0] -= 2 * margin_m
            extended_breakpoints_m[-1] += margin_m
        else:
            extended_breakpoints_m[0] -= 2 * margin_m
            extended_breakpoints_m[-1] += 2 * margin_m
        return cls._m_to_points(breakpoints_m=extended_breakpoints_m, step_length=plan.step_length)

    @classmethod
    def _m_to_points(cls, breakpoints_m: list[float], step_length: int) -> npt.NDArray[np.int_]:
        bpts_m = np.array(breakpoints_m)
        start_point = int(bpts_m[0] / cls.APPROX_BASE_STEP_LENGTH_M)
        num_points = (bpts_m[-1] - bpts_m[0]) / (cls.APPROX_BASE_STEP_LENGTH_M * step_length)
        bpts = (
            np.round((num_points / (bpts_m[-1] - bpts_m[0]) * (bpts_m - bpts_m[0]))) + start_point
        )
        return bpts  # type: ignore[no-any-return]

    @classmethod
    def _update_processor_mode(
        cls, processor_specs: list[ProcessorSpec], processor_mode: ProcessorMode
    ) -> list[ProcessorSpec]:
        updated_specs = []
        for spec in processor_specs:
            new_processor_config = attrs.evolve(
                spec.processor_config, processor_mode=processor_mode
            )
            updated_specs.append(attrs.evolve(spec, processor_config=new_processor_config))
        return updated_specs
