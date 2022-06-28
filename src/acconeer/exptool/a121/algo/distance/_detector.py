from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoConfigBase

from ._aggregator import Aggregator, AggregatorConfig, PeakSortingMethod, ProcessorSpec
from ._processors import (
    DEFAULT_CFAR_ONE_SIDED,
    DEFAULT_FIXED_THRESHOLD_VALUE,
    DEFAULT_THRESHOLD_SENSITIVITY,
    MeasurementType,
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorMode,
    ProcessorResult,
    ThresholdMethod,
)


@attrs.frozen(kw_only=True)
class SubsweepGroupPlan:
    step_length: int = attrs.field()
    breakpoints: list[int] = attrs.field()
    profile: a121.Profile = attrs.field()


Plan = Dict[MeasurementType, List[SubsweepGroupPlan]]


@attrs.mutable(kw_only=True)
class DetectorContext:
    direct_leakage: Optional[npt.NDArray[np.complex_]] = attrs.field(default=None)
    phase_jitter_comp_reference: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    recorded_thresholds: Optional[List[npt.NDArray[np.float_]]] = attrs.field(default=None)
    recorded_threshold_session_config_used: Optional[a121.SessionConfig] = attrs.field(
        default=None
    )
    close_range_session_config_used: Optional[a121.SessionConfig] = attrs.field(default=None)

    # TODO: Make recorded_thresholds Optional[List[Optional[npt.NDArray[np.float_]]]]


@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=0.2)
    end_m: float = attrs.field(default=1.0)
    max_step_length: Optional[int] = attrs.field(default=None)  # TODO: Check validity
    max_profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_5, converter=a121.Profile)
    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR,
        converter=ThresholdMethod,
    )
    peaksorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.STRONGEST,
        converter=PeakSortingMethod,
    )

    num_frames_in_recorded_threshold: int = attrs.field(default=20)
    fixed_threshold_value: float = attrs.field(default=DEFAULT_FIXED_THRESHOLD_VALUE)
    threshold_sensitivity: float = attrs.field(default=DEFAULT_THRESHOLD_SENSITIVITY)
    cfar_one_sided: bool = attrs.field(default=DEFAULT_CFAR_ONE_SIDED)


@attrs.frozen(kw_only=True)
class DetectorResult:
    distances: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    processor_results: list[ProcessorResult] = attrs.field()


class Detector:

    MIN_DIST_M = {
        a121.Profile.PROFILE_1: 0.10,
        a121.Profile.PROFILE_2: 0.28,
        a121.Profile.PROFILE_3: 0.56,
        a121.Profile.PROFILE_4: 0.76,
        a121.Profile.PROFILE_5: 1.28,
    }
    MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN = 4.0
    VALID_STEP_LENGTHS_IN_COARSE = [1, 2, 3, 4, 6, 8, 12, 24]
    NUM_POINTS_IN_COARSE = 24
    NUM_SUBSWEEPS_IN_SENSOR_CONFIG = 4

    session_config: a121.SessionConfig
    processor_specs: List[ProcessorSpec]
    context: DetectorContext

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        detector_config: DetectorConfig,
        context: Optional[DetectorContext] = None,
    ) -> None:
        self.client = client
        self.sensor_id = sensor_id
        self.detector_config = detector_config
        self.started = False

        if context is None:
            self.context = DetectorContext()
        else:
            self.context = context

        self.aggregator: Optional[Aggregator] = None

        self.update_config(self.detector_config)

    def calibrate_close_range(self) -> None:
        if self.started:
            raise RuntimeError("Already started")
        if self.processor_specs is None:
            raise ValueError("Processor specification not defined")
        if self.session_config is None:
            raise ValueError("Session config not defined")

        close_range_spec = self._filter_close_range_spec(self.processor_specs)
        spec = self._update_processor_mode(close_range_spec, ProcessorMode.LEAKAGE_CALIBRATION)

        # Note - Setup with full session_config to match the structure of spec
        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)

        aggregator = Aggregator(
            session_config=self.session_config,
            extended_metadata=extended_metadata,
            aggregator_config=AggregatorConfig(),
            specs=spec,
        )

        self.client.start_session()
        extended_result = self.client.get_next()
        assert isinstance(extended_result, list)
        aggregator_result = aggregator.process(extended_result=extended_result)
        self.client.stop_session()
        (processor_result,) = aggregator_result.processor_results
        self.context.direct_leakage = processor_result.direct_leakage
        assert processor_result.phase_jitter_comp_reference is not None
        self.context.phase_jitter_comp_reference = processor_result.phase_jitter_comp_reference
        self.context.close_range_session_config_used = self.session_config

    def record_threshold(self) -> None:
        if self.started:
            raise RuntimeError("Already started")
        if self.processor_specs is None:
            raise ValueError("Processor specification not defined")
        if self.session_config is None:
            raise ValueError("Session config not defined")

        # TODO: Ignore/override threshold method while recording threshold

        specs_updated = self._update_processor_mode(
            self.processor_specs, ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
        )
        specs = self._add_context_to_processor_spec(specs_updated)

        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)

        aggregator = Aggregator(
            session_config=self.session_config,
            extended_metadata=extended_metadata,
            aggregator_config=AggregatorConfig(),
            specs=specs,
        )

        aggregator_result = None
        self.client.start_session()
        for _ in range(self.detector_config.num_frames_in_recorded_threshold):
            extended_result = self.client.get_next()
            assert isinstance(extended_result, list)
            aggregator_result = aggregator.process(extended_result=extended_result)
        self.client.stop_session()

        assert aggregator_result is not None

        self.context.recorded_thresholds = []
        for processor_result in aggregator_result.processor_results:
            threshold = processor_result.recorded_threshold
            assert threshold is not None  # Since we know what mode the processor is running in
            self.context.recorded_thresholds.append(threshold)
        self.context.recorded_threshold_session_config_used = self.session_config

    @staticmethod
    def _close_range_calibrated(context: DetectorContext) -> bool:
        has_dl = context.direct_leakage is not None
        has_pjcr = context.phase_jitter_comp_reference is not None

        if has_dl != has_pjcr:
            raise RuntimeError

        return has_dl and has_pjcr

    @staticmethod
    def _recorded_threshold_calibrated(context: DetectorContext) -> bool:
        return context.recorded_thresholds is not None

    @classmethod
    def _has_close_range_measurement(self, config: DetectorConfig) -> bool:
        (
            _,
            specs,
        ) = self._detector_to_session_config_and_processor_specs(config=config, sensor_id=1)
        return MeasurementType.CLOSE_RANGE in [
            spec.processor_config.measurement_type for spec in specs
        ]

    @classmethod
    def _has_recorded_threshold_mode(self, config: DetectorConfig) -> bool:
        (
            _,
            processor_specs,
        ) = self._detector_to_session_config_and_processor_specs(config=config, sensor_id=1)
        return ThresholdMethod.RECORDED in [
            spec.processor_config.threshold_method for spec in processor_specs
        ]

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Already started")

        self._ensure_detector_is_calibrated()
        self._ensure_matching_session_config()

        specs = self._add_context_to_processor_spec(self.processor_specs)
        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)

        aggregator_config = AggregatorConfig(
            peak_sorting_method=self.detector_config.peaksorting_method
        )
        self.aggregator = Aggregator(
            session_config=self.session_config,
            extended_metadata=extended_metadata,
            aggregator_config=aggregator_config,
            specs=specs,
        )

        self.client.start_session()
        self.started = True

    def get_next(self) -> DetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        assert self.aggregator is not None

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

        self.started = False

    @classmethod
    def _detector_to_session_config_and_processor_specs(
        cls, config: DetectorConfig, sensor_id: int
    ) -> Tuple[a121.SessionConfig, list[ProcessorSpec]]:
        processor_specs = []
        groups = []
        group_index = 0

        plans = cls._create_group_plans(config)

        if MeasurementType.CLOSE_RANGE in plans:
            sensor_config = cls._close_subsweep_group_plans_to_sensor_config(
                plans[MeasurementType.CLOSE_RANGE]
            )
            groups.append({sensor_id: sensor_config})
            processor_specs.append(
                ProcessorSpec(
                    processor_config=ProcessorConfig(
                        threshold_method=ThresholdMethod.RECORDED,
                        measurement_type=MeasurementType.CLOSE_RANGE,
                    ),
                    group_index=group_index,
                    sensor_id=sensor_id,
                    subsweep_indexes=[0, 1],
                )
            )
            group_index += 1

        if MeasurementType.FAR_RANGE in plans:
            (
                sensor_config,
                processor_specs_subsweep_indexes,
            ) = cls._far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
                plans[MeasurementType.FAR_RANGE]
            )
            groups.append({sensor_id: sensor_config})

            processor_config = ProcessorConfig(
                threshold_method=config.threshold_method,
                fixed_threshold_value=config.fixed_threshold_value,
                threshold_sensitivity=config.threshold_sensitivity,
                cfar_one_sided=config.cfar_one_sided,
            )

            for subsweep_indexes in processor_specs_subsweep_indexes:
                processor_specs.append(
                    ProcessorSpec(
                        processor_config=processor_config,
                        group_index=group_index,
                        sensor_id=sensor_id,
                        subsweep_indexes=subsweep_indexes,
                    )
                )

        return (a121.SessionConfig(groups, extended=True), processor_specs)

    @classmethod
    def _create_group_plans(
        cls, config: DetectorConfig
    ) -> Dict[MeasurementType, List[SubsweepGroupPlan]]:
        """
        Create dictionary containing group plans for close and far range measurements.

        Constants used:
        - MIN_DIST_M defines the shortest distance possible to measure free of leakage.

        Outline of logic:
        - If the start is closer than the transition point, a close range subsweep plan is added.
        - If the end is further away than the transition point, far range subsweep plans are added.
        - max_profile is used in the far range region to achive high SNR and low power consumption.
        - A shorter profile is used between the transition point and the MIN_DIST_M of max_profile.
        """

        min_dist_m = cls._add_to_min_dist_m(config)
        transition_m = list(min_dist_m.values())[0]

        plans = {}

        if config.start_m < transition_m:
            profile = a121.Profile.PROFILE_1
            step_length = cls._limit_step_length(profile, config.max_step_length)
            breakpoints = cls._m_to_points([config.start_m, transition_m], step_length)

            has_neighbour = (False, transition_m < config.end_m)

            extended_breakpoints = cls._add_margin_to_breakpoints(
                profile, step_length, breakpoints, has_neighbour, config
            )
            plans[MeasurementType.CLOSE_RANGE] = [
                SubsweepGroupPlan(
                    step_length=step_length,
                    breakpoints=extended_breakpoints,
                    profile=profile,
                )
            ]

        far_subgroup_plans = []
        far_range_start_m = np.max([config.start_m, transition_m])
        if far_range_start_m <= min_dist_m[config.max_profile]:
            min_dists_m = np.array(list(min_dist_m.values()))
            min_dists_profiles = np.array(list(min_dist_m.keys()))
            (viable_profile_idx,) = np.where(min_dists_m <= far_range_start_m)
            profile_to_be_used = min_dists_profiles[viable_profile_idx[-1]]

            end_m = min(config.end_m, min_dist_m[config.max_profile])
            step_length = cls._limit_step_length(profile_to_be_used, config.max_step_length)
            breakpoints = cls._m_to_points([far_range_start_m, end_m], step_length)

            has_neighbour = (len(plans) != 0, min_dist_m[config.max_profile] < end_m)

            extended_breakpoints = cls._add_margin_to_breakpoints(
                profile_to_be_used, step_length, breakpoints, has_neighbour, config
            )
            far_subgroup_plans.append(
                SubsweepGroupPlan(
                    step_length=step_length,
                    breakpoints=extended_breakpoints,
                    profile=profile_to_be_used,
                )
            )

        if min_dist_m[config.max_profile] < config.end_m:
            breakpoints_m = np.linspace(
                min_dist_m[config.max_profile],
                config.end_m,
                cls.NUM_SUBSWEEPS_IN_SENSOR_CONFIG + 1 - len(far_subgroup_plans),
            ).tolist()

            profile = config.max_profile
            step_length = cls._limit_step_length(config.max_profile, config.max_step_length)
            breakpoints = cls._m_to_points(breakpoints_m, step_length)

            has_neighbour = (len(plans) != 0 or len(far_subgroup_plans) != 0, False)

            extended_breakpoints = cls._add_margin_to_breakpoints(
                profile, step_length, breakpoints, has_neighbour, config
            )
            far_subgroup_plans.append(
                SubsweepGroupPlan(
                    step_length=step_length,
                    breakpoints=extended_breakpoints,
                    profile=profile,
                )
            )

        if len(far_subgroup_plans) != 0:
            plans[MeasurementType.FAR_RANGE] = far_subgroup_plans

        return plans

    @classmethod
    def _add_to_min_dist_m(cls, config: DetectorConfig) -> Dict[a121.Profile, float]:
        min_dist_m = {}
        for profile, min_dist in cls.MIN_DIST_M.items():
            min_dist_m[profile] = min_dist
            if config.threshold_method == ThresholdMethod.CFAR:
                step_length = cls._limit_step_length(profile, config.max_step_length)
                cfar_margin_m = (
                    Processor.calc_cfar_margin(profile, step_length)
                    * step_length
                    * Processor.APPROX_BASE_STEP_LENGTH_M
                )
                min_dist_m[profile] += cfar_margin_m
        return min_dist_m

    @classmethod
    def _add_margin_to_breakpoints(
        cls,
        profile: a121.Profile,
        step_length: int,
        base_bpts: list[int],
        has_neighbour: Tuple[bool, bool],
        config: DetectorConfig,
    ) -> list[int]:
        """
        Add points to segment edges based on their position.

        1. Add one margin to each segment for distance filter initialization
        2. Add an additional margin to segments with neighbouring segments for segment overlap
        """

        margin_p = Processor.distance_filter_edge_margin(profile, step_length) * step_length
        left_margin = margin_p
        right_margin = margin_p

        if has_neighbour[0]:
            left_margin += margin_p

        if has_neighbour[1]:
            right_margin += margin_p

        if config.threshold_method == ThresholdMethod.CFAR:
            cfar_margin = Processor.calc_cfar_margin(profile, step_length) * step_length
            left_margin += cfar_margin
            right_margin += cfar_margin

        bpts = copy.copy(base_bpts)
        bpts[0] -= left_margin
        bpts[-1] += right_margin

        return bpts

    @classmethod
    def _limit_step_length(cls, profile: a121.Profile, user_limit: Optional[int]) -> int:
        fwhm_p = Processor.ENVELOPE_FWHM_M[profile] / Processor.APPROX_BASE_STEP_LENGTH_M
        limit = int(fwhm_p / cls.MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN)

        if user_limit is not None:
            limit = min(user_limit, limit)

        if limit < cls.NUM_POINTS_IN_COARSE:
            # TODO: Pick the longest, but not longer than limit
            idx_closest = np.argmin(np.abs(np.array(cls.VALID_STEP_LENGTHS_IN_COARSE) - limit))
            return cls.VALID_STEP_LENGTHS_IN_COARSE[idx_closest]
        else:
            return (limit // cls.NUM_POINTS_IN_COARSE) * cls.NUM_POINTS_IN_COARSE

    @classmethod
    def _close_subsweep_group_plans_to_sensor_config(
        cls, plan_: List[SubsweepGroupPlan]
    ) -> a121.SensorConfig:
        (plan,) = plan_
        subsweeps = []
        subsweeps.append(
            a121.SubsweepConfig(
                start_point=0,
                num_points=1,
                step_length=1,
                profile=a121.Profile.PROFILE_4,
                hwaas=4,
                receiver_gain=15,
                phase_enhancement=True,
                enable_loopback=True,
            )
        )
        num_points = int((plan.breakpoints[1] - plan.breakpoints[0]) / plan.step_length)
        subsweeps.append(
            a121.SubsweepConfig(
                start_point=plan.breakpoints[0],
                num_points=num_points,
                step_length=plan.step_length,
                profile=plan.profile,
                hwaas=4,
                receiver_gain=5,
                phase_enhancement=True,
            )
        )
        return a121.SensorConfig(subsweeps=subsweeps, sweeps_per_frame=10)

    @classmethod
    def _far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
        cls, subsweep_group_plans: list[SubsweepGroupPlan]
    ) -> Tuple[a121.SensorConfig, list[list[int]]]:
        subsweeps = []
        processor_specs_subsweep_indexes = []
        subsweep_idx = 0
        for plan in subsweep_group_plans:
            subsweep_indexes = []
            for bp_idx in range(len(plan.breakpoints) - 1):
                num_points = int(
                    (plan.breakpoints[bp_idx + 1] - plan.breakpoints[bp_idx]) / plan.step_length
                )
                subsweeps.append(
                    a121.SubsweepConfig(
                        start_point=plan.breakpoints[bp_idx],
                        num_points=num_points,
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
        return (
            a121.SensorConfig(subsweeps=subsweeps, sweeps_per_frame=1),
            processor_specs_subsweep_indexes,
        )

    @classmethod
    def _m_to_points(cls, breakpoints_m: list[float], step_length: int) -> list[int]:
        bpts_m = np.array(breakpoints_m)
        start_point = int(bpts_m[0] / Processor.APPROX_BASE_STEP_LENGTH_M)
        num_steps = (bpts_m[-1] - bpts_m[0]) / (Processor.APPROX_BASE_STEP_LENGTH_M)
        bpts = num_steps / (bpts_m[-1] - bpts_m[0]) * (bpts_m - bpts_m[0]) + start_point
        return [(bpt // step_length) * step_length for bpt in bpts]

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

    @classmethod
    def _filter_close_range_spec(cls, specs: list[ProcessorSpec]) -> list[ProcessorSpec]:
        NUM_CLOSE_RANGE_SPECS = 1
        close_range_specs = []
        for spec in specs:
            if spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
                close_range_specs.append(spec)
        if len(close_range_specs) != NUM_CLOSE_RANGE_SPECS:
            raise ValueError("Incorrect subsweep config for close range measurement")

        return close_range_specs

    def _add_context_to_processor_spec(
        self, processor_specs: list[ProcessorSpec]
    ) -> list[ProcessorSpec]:
        """
        Add context to ProcessorSpec object, based on the corresponding processor config.

        1. Close range measurement and distance estimation -> Recorded threshold, direct
        leakage and phase jitter compensation reference.
        2. Close range measurement and recorded threshold calibration -> Direct leakage and
        phase jitter compensation reference.
        3. Far range measurement and recorded threshold calibration -> Recorded threshold.

        If not one of these cases, add the unaltered processor specification.
        """

        ERR_MESSAGE_CLOSE_RANGE_ERR = "Close range calibration not performed"
        ERR_MESSAGE_RECORDED = "Recorded threshold calibration not performed"

        updated_specs: List[ProcessorSpec] = []

        for idx, spec in enumerate(processor_specs):

            if (
                spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE
                and spec.processor_config.processor_mode == ProcessorMode.DISTANCE_ESTIMATION
            ):
                if not self.close_range_calibrated:
                    raise Exception(ERR_MESSAGE_CLOSE_RANGE_ERR)

                if (
                    not self.recorded_threshold_calibrated
                    or self.context.recorded_thresholds is None
                ):
                    raise Exception(ERR_MESSAGE_RECORDED)

                context = ProcessorContext(
                    recorded_threshold=self.context.recorded_thresholds[idx],
                    direct_leakage=self.context.direct_leakage,
                    phase_jitter_comp_ref=self.context.phase_jitter_comp_reference,
                )
                updated_specs.append(attrs.evolve(spec, processor_context=context))
            elif (
                spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE
                and spec.processor_config.processor_mode
                == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
            ):
                if not self.close_range_calibrated:
                    raise Exception(ERR_MESSAGE_CLOSE_RANGE_ERR)

                context = ProcessorContext(
                    direct_leakage=self.context.direct_leakage,
                    phase_jitter_comp_ref=self.context.phase_jitter_comp_reference,
                )
                updated_specs.append(attrs.evolve(spec, processor_context=context))
            elif (
                spec.processor_config.measurement_type == MeasurementType.FAR_RANGE
                and spec.processor_config.threshold_method == ThresholdMethod.RECORDED
            ):
                if (
                    not self.recorded_threshold_calibrated
                    or self.context.recorded_thresholds is None
                ):
                    raise Exception(ERR_MESSAGE_RECORDED)

                context = ProcessorContext(
                    recorded_threshold=self.context.recorded_thresholds[idx]
                )
                updated_specs.append(attrs.evolve(spec, processor_context=context))
            else:
                updated_specs.append(spec)
        return updated_specs

    def _ensure_detector_is_calibrated(self) -> None:
        """
        Checks if required calibration has been performed

        Calibration is requred in the following two cases:
        1. Close range measurement requires direct leakage, phase jitter compensation
        and recorded threshold calibration
        2. Recorded threshold requires recorded threshold calibration to be performed
        """

        if self._has_close_range_measurement(self.detector_config):
            if not (
                self._close_range_calibrated(self.context)
                and self._recorded_threshold_calibrated(self.context)
            ):
                raise ValueError("Detector not calibrated.")

        if self._has_recorded_threshold_mode(
            self.detector_config
        ) and not self._recorded_threshold_calibrated(self.context):
            raise ValueError("Detector not calibrated.")

    def _ensure_matching_session_config(self) -> None:
        """
        Check if session config matches session config used during calibration
        """

        if self._has_close_range_measurement(self.detector_config):
            if self.context.close_range_session_config_used != self.session_config:
                raise ValueError("Session config does not match config used during calibration")

        if self._has_recorded_threshold_mode(self.detector_config):
            if self.context.recorded_threshold_session_config_used != self.session_config:
                raise ValueError("Session config does not match config used during calibration")
