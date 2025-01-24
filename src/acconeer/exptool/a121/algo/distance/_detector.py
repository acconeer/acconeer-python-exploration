# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import copy
import enum
import warnings
from typing import Any, Dict, List, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc
from packaging.version import Version

from acconeer.exptool import a121, opser
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.attrs import attrs_optional_ndarray_isclose
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    RLG_PER_HWAAS_MAP,
    AlgoConfigBase,
    Controller,
    PeakSortingMethod,
    ReflectorShape,
    calc_processing_gain,
    get_distance_filter_edge_margin,
    select_prf,
)

from ._aggregator import Aggregator, AggregatorConfig, ProcessorSpec
from ._context import (
    CloseRangeCalibration,
    DetectorContext,
    NoiseCalibration,
    OffsetCalibration,
    RecordedThresholdCalibration,
    detector_context_timeline,
)
from ._processors import (
    DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE,
    DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE,
    DEFAULT_THRESHOLD_SENSITIVITY,
    MeasurementType,
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
    ThresholdMethod,
)


@attrs.frozen(kw_only=True)
class DetectorStatus:
    detector_state: DetailedStatus
    ready_to_start: bool


class DetailedStatus(enum.Enum):
    OK = enum.auto()
    END_LESSER_THAN_START = enum.auto()
    SENSOR_IDS_NOT_UNIQUE = enum.auto()
    CONTEXT_MISSING = enum.auto()
    CALIBRATION_MISSING = enum.auto()
    CONFIG_MISMATCH = enum.auto()


@attrs.frozen(kw_only=True)
class SubsweepGroupPlan:
    step_length: int = attrs.field()
    breakpoints: list[int] = attrs.field()
    profile: a121.Profile = attrs.field()
    hwaas: list[int] = attrs.field()


Plan = Dict[MeasurementType, List[SubsweepGroupPlan]]

PRF_REMOVED_ET_VERSION = Version("v7.13.2")


@attributes_doc
@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=0.25)
    """Start of measurement range in meters."""

    end_m: float = attrs.field(default=3.0)
    """End of measurement range in meters."""

    max_step_length: Optional[int] = attrs.field(default=None)
    """If set, limits the step length.

    If no argument is provided, the step length is automatically calculated based on the profile.

    Reducing the step length increases SNR through more efficient distance filtering, while
    increasing the measurement time and the processing load.
    """

    max_profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_5, converter=a121.Profile)
    """Specifies the longest allowed profile.

    If no argument is provided, the highest possible profile without interference of direct
    leakage is used to maximize SNR.

    A lower profile improves the radial resolution.
    """

    close_range_leakage_cancellation: bool = attrs.field(default=False)
    """Enable close range leakage cancellation logic.

    Close range leakage cancellation refers to the process of measuring close to the
    sensor(<100mm) by first characterizing the direct leakage, and then subtracting it
    from the measured sweep in order to isolate the signal component of interest.

    The close range leakage cancellation process requires the sensor to be installed in its
    intended geometry with free space in front of the sensor during detector calibration.
    """

    signal_quality: float = attrs.field(default=15.0)
    """Signal quality (dB).

    High quality equals higher HWAAS and better SNR but increases power consumption."""

    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR,
        converter=ThresholdMethod,
    )
    """Threshold method"""

    peaksorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.STRONGEST,
        converter=PeakSortingMethod,
    )
    """Sorting method of estimated distances.

    The distance estimates are sorted according to the selected strategy, before being return
    by th application.
    """

    reflector_shape: ReflectorShape = attrs.field(
        default=ReflectorShape.GENERIC,
        converter=ReflectorShape,
    )
    """Reflector shape."""

    num_frames_in_recorded_threshold: int = attrs.field(default=100)
    """Number of frames used when calibrating threshold.

    A lower number reduce calibration time and a higher number results in a more statistically
    significant threshold.
    """

    fixed_threshold_value: float = attrs.field(default=DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE)
    """Value of fixed amplitude threshold."""

    fixed_strength_threshold_value: float = attrs.field(
        default=DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE
    )
    """Value of fixed strength threshold."""

    threshold_sensitivity: float = attrs.field(default=DEFAULT_THRESHOLD_SENSITIVITY)
    """Sensitivity of threshold.

    High sensitivity equals low detection threshold, low sensitivity equals high detection
    threshold."""

    update_rate: Optional[float] = attrs.field(default=50.0)
    """Sets the detector update rate."""

    @start_m.validator
    def _(self, _: Any, value: float) -> None:
        if value < Detector.MIN_DIST_M:
            msg = f"Cannot start measurements closer than {Detector.MIN_DIST_M}m"
            raise ValueError(msg)

    @end_m.validator
    def _(self, _: Any, value: float) -> None:
        if value > Detector.MAX_DIST_M:
            msg = f"Cannot measure further than {Detector.MAX_DIST_M}m"
            raise ValueError(msg)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if self.end_m < self.start_m:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "start_m",
                    "Must be smaller than 'Range end'",
                )
            )

            validation_results.append(
                a121.ValidationError(
                    self,
                    "end_m",
                    "Must be greater than 'Range start'",
                )
            )

        if self.max_step_length is not None and (
            not utils.is_divisor_of(24, self.max_step_length)
            and not utils.is_multiple_of(24, self.max_step_length)
        ):
            valid_step_length = next(
                sl
                for sl in range(self.max_step_length, 0, -1)
                if utils.is_divisor_of(24, sl) or utils.is_multiple_of(24, sl)
            )
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "max_step_length",
                    "Actual step length will be rounded down "
                    + f"to the closest valid step length ({valid_step_length}).",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class DetectorResult:
    distances: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    """Estimated distances (m), sorted according to the selected peak sorting strategy."""

    strengths: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    """Estimated reflector strengths (dB) corresponding to the peak amplitude of the estimated
    distances.
    """

    near_edge_status: Optional[bool] = attrs.field(default=None)
    """Boolean indicating an object close to the start edge, located outside of the
    measurement range.
    """

    calibration_needed: Optional[bool] = attrs.field(default=None)
    """Indication of calibration needed. The sensor calibration needs to be redone if this
    indication is set.

    A sensor calibration should be followed by a detector calibration update, by calling
    :func:`update_detector_calibration`.
    """

    temperature: Optional[int] = attrs.field(default=None)
    """Temperature in sensor during measurement (in degree Celsius). Notice that this has poor
    absolute accuracy.
    """

    processor_results: List[ProcessorResult] = attrs.field()
    """Processing result. Used for visualization in Exploration Tool."""

    service_extended_result: List[Dict[int, a121.Result]] = attrs.field()
    """Service extended result. Used for visualization in Exploration Tool."""


class Detector(Controller[DetectorConfig, Dict[int, DetectorResult]]):
    """Distance detector
    :param client: Client
    :param sensor_id: Sensor id
    :param detector_config: Detector configuration
    :param context: Detector context
    """

    MIN_DIST_M = 0.0
    MAX_DIST_M = 23.0
    MIN_LEAKAGE_FREE_DIST_M = {
        a121.Profile.PROFILE_1: 0.12,
        a121.Profile.PROFILE_2: 0.28,
        a121.Profile.PROFILE_3: 0.56,
        a121.Profile.PROFILE_4: 0.76,
        a121.Profile.PROFILE_5: 1.28,
    }
    MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN = 4.0
    VALID_STEP_LENGTHS = [1, 2, 3, 4, 6, 8, 12, 24]
    NUM_SUBSWEEPS_IN_SENSOR_CONFIG = 4

    MAX_HWAAS = 511
    MIN_HWAAS = 1
    HWAAS_MIN_DISTANCE = 1.0

    session_config: a121.SessionConfig
    processor_specs: List[ProcessorSpec]
    context: DetectorContext

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_ids: list[int],
        detector_config: DetectorConfig,
        context: Optional[DetectorContext] = None,
    ) -> None:
        super().__init__(client=client, config=detector_config)
        self.sensor_ids = sensor_ids
        self.started = False

        if context is None or not bool(context.sensor_ids):
            self.context = DetectorContext(sensor_ids=self.sensor_ids)
        else:
            self.context = context

        self.aggregator: Optional[Aggregator] = None

        self.update_config(self.config)

    def _validate_ready_for_calibration(self) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)
        if self.processor_specs is None:
            msg = "Processor specification not defined"
            raise ValueError(msg)
        if self.session_config is None:
            msg = "Session config not defined"
            raise ValueError(msg)

    def calibrate_detector(self) -> None:
        """Run the required detector calibration routines, based on the detector config."""

        self._validate_ready_for_calibration()

        self.context.offset_calibration = OffsetCalibration.create(self.client, self.sensor_ids)

        self.context.noise_calibration = NoiseCalibration.create(
            self.client, self.sensor_ids, self.session_config
        )

        if self._has_close_range_measurement(self.config):
            self.context.close_range_calibration = CloseRangeCalibration.create(
                self.client, self.session_config
            )

        if self._has_close_range_measurement(self.config) or self._has_recorded_threshold_mode(
            self.config, self.sensor_ids
        ):
            self.context.recorded_threshold_calibration = RecordedThresholdCalibration.create(
                self.client, self.session_config, self.config.num_frames_in_recorded_threshold
            )

        self.context.session_config_used_during_calibration = self.session_config

    def update_detector_calibration(self) -> None:
        """Do a detector calibration update by running a subset of the calibration routines.

        Once the detector is calibrated, by calling :func:`calibrate_detector`, a sensor
        calibration should be followed by a detector calibration update.
        """

        self._validate_ready_for_calibration()

        self.context.offset_calibration = OffsetCalibration.create(self.client, self.sensor_ids)

    @staticmethod
    def _get_sensor_calibrations(context: DetectorContext) -> dict[int, a121.SensorCalibration]:
        return (
            context.close_range_calibration.sensor_calibrations
            if context.close_range_calibration is not None
            else {}
        )

    @classmethod
    def get_detector_status(
        cls,
        config: DetectorConfig,
        context: DetectorContext,
        sensor_ids: list[int],
    ) -> DetectorStatus:
        """Returns the detector status along with the detector state."""

        if config.end_m < config.start_m:
            return DetectorStatus(
                detector_state=DetailedStatus.END_LESSER_THAN_START,
                ready_to_start=False,
            )

        if len(sensor_ids) != len(set(sensor_ids)):
            return DetectorStatus(
                detector_state=DetailedStatus.SENSOR_IDS_NOT_UNIQUE,
                ready_to_start=False,
            )

        if len(context.sensor_ids) == 0:
            return DetectorStatus(
                detector_state=DetailedStatus.CONTEXT_MISSING,
                ready_to_start=False,
            )

        (
            session_config,
            _,
        ) = cls._detector_to_session_config_and_processor_specs(
            config=config, sensor_ids=sensor_ids
        )

        # Offset calibration is always performed as a part of the detector calibration process.
        # Use this as indication whether detector calibration has been performed.
        calibration_missing = np.any(
            [context.offset_calibration is None for sensor_id in context.sensor_ids]
        )
        config_mismatch = context.session_config_used_during_calibration != session_config

        if calibration_missing:
            detector_state = DetailedStatus.CALIBRATION_MISSING
        elif config_mismatch:
            detector_state = DetailedStatus.CONFIG_MISMATCH
        else:
            detector_state = DetailedStatus.OK

        return DetectorStatus(
            detector_state=detector_state,
            ready_to_start=(detector_state == DetailedStatus.OK),
        )

    @staticmethod
    def _close_range_calibrated(context: DetectorContext) -> bool:
        return context.close_range_calibration is not None

    @staticmethod
    def _recorded_threshold_calibrated(context: DetectorContext) -> bool:
        return context.recorded_threshold_calibration is not None

    @classmethod
    def _has_close_range_measurement(self, config: DetectorConfig) -> bool:
        # sensor_ids=[1] as the detector is running the same config for all sensors.
        (
            _,
            specs,
        ) = self._detector_to_session_config_and_processor_specs(config=config, sensor_ids=[1])
        return MeasurementType.CLOSE_RANGE in [
            spec.processor_config.measurement_type for spec in specs
        ]

    @classmethod
    def _has_recorded_threshold_mode(self, config: DetectorConfig, sensor_ids: list[int]) -> bool:
        (
            _,
            processor_specs,
        ) = self._detector_to_session_config_and_processor_specs(
            config=config, sensor_ids=sensor_ids
        )
        return ThresholdMethod.RECORDED in [
            spec.processor_config.threshold_method for spec in processor_specs
        ]

    def start(
        self,
        recorder: Optional[a121.Recorder] = None,
        *,
        _algo_group: Optional[h5py.Group] = None,
    ) -> None:
        """Method for setting up measurement session."""

        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        status = self.get_detector_status(self.config, self.context, self.sensor_ids)

        if not status.ready_to_start:
            msg = f"Not ready to start ({status.detector_state.name})"
            raise RuntimeError(msg)
        specs = self._add_context_to_processor_spec()

        sensor_calibration = self._get_sensor_calibrations(self.context)

        extended_metadata = self.client.setup_session(
            self.session_config, calibrations=sensor_calibration
        )

        assert isinstance(extended_metadata, list)
        assert np.all(
            [self.context.offset_calibration is not None for sensor_id in self.context.sensor_ids]
        )
        aggregator_config = AggregatorConfig(peak_sorting_method=self.config.peaksorting_method)
        self.aggregators = {
            sensor_id: Aggregator(
                session_config=self.session_config,
                extended_metadata=extended_metadata,
                config=aggregator_config,
                specs=specs[sensor_id],
                sensor_id=sensor_id,
            )
            for sensor_id in self.sensor_ids
        }

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                if _algo_group is None:
                    _algo_group = recorder.require_algo_group("distance_detector")

                _record_algo_data(
                    _algo_group,
                    self.sensor_ids,
                    self.config,
                    self.context,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

            self.client.attach_recorder(recorder)

        self.client.start_session()
        self.started = True

    def get_next(self) -> Dict[int, DetectorResult]:
        """Called from host to get next measurement."""
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        assert self.aggregators is not None

        extended_result = self.client.get_next()
        assert isinstance(extended_result, list)

        aggregator_results = {
            sensor_id: self.aggregators[sensor_id].process(extended_result=extended_result)
            for sensor_id in self.sensor_ids
        }

        result = {
            sensor_id: DetectorResult(
                strengths=aggregator_results[sensor_id].estimated_strengths,
                distances=aggregator_results[sensor_id].estimated_distances,
                near_edge_status=aggregator_results[sensor_id].near_edge_status,
                calibration_needed=extended_result[0][sensor_id].calibration_needed,
                temperature=extended_result[0][sensor_id].temperature,
                processor_results=aggregator_results[sensor_id].processor_results,
                service_extended_result=aggregator_results[sensor_id].service_extended_result,
            )
            for sensor_id in self.sensor_ids
        }

        return result

    def update_config(self, config: DetectorConfig) -> None:
        """Updates the session config and processor specification based on the detector
        configuration."""
        (
            self.session_config,
            self.processor_specs,
        ) = self._detector_to_session_config_and_processor_specs(
            config=config, sensor_ids=self.sensor_ids
        )

    def stop(self) -> Any:
        """Stops the measurement session."""
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        self.client.stop_session()
        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()

        self.started = False

        return recorder_result

    @classmethod
    def _detector_to_session_config_and_processor_specs(
        cls, config: DetectorConfig, sensor_ids: list[int]
    ) -> Tuple[a121.SessionConfig, list[ProcessorSpec]]:
        processor_specs = []
        groups = []
        group_index = 0

        plans = cls._create_group_plans(config)
        prf = cls._get_max_prf(plans)

        if MeasurementType.CLOSE_RANGE in plans:
            sensor_config = cls._close_subsweep_group_plans_to_sensor_config(
                plans[MeasurementType.CLOSE_RANGE], prf
            )
            groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})
            processor_specs.append(
                ProcessorSpec(
                    processor_config=ProcessorConfig(
                        threshold_method=ThresholdMethod.RECORDED,
                        measurement_type=MeasurementType.CLOSE_RANGE,
                        threshold_sensitivity=config.threshold_sensitivity,
                        reflector_shape=config.reflector_shape,
                    ),
                    group_index=group_index,
                    subsweep_indexes=[0, 1],
                )
            )
            group_index += 1

        if MeasurementType.FAR_RANGE in plans:
            (
                sensor_config,
                processor_specs_subsweep_indexes,
            ) = cls._far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
                plans[MeasurementType.FAR_RANGE], prf
            )
            groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})

            processor_config = ProcessorConfig(
                threshold_method=config.threshold_method,
                fixed_threshold_value=config.fixed_threshold_value,
                fixed_strength_threshold_value=config.fixed_strength_threshold_value,
                threshold_sensitivity=config.threshold_sensitivity,
                reflector_shape=config.reflector_shape,
            )

            for subsweep_indexes in processor_specs_subsweep_indexes:
                processor_specs.append(
                    ProcessorSpec(
                        processor_config=processor_config,
                        group_index=group_index,
                        subsweep_indexes=subsweep_indexes,
                    )
                )

        return (
            a121.SessionConfig(groups, extended=True, update_rate=config.update_rate),
            processor_specs,
        )

    @classmethod
    def _create_group_plans(
        cls, config: DetectorConfig
    ) -> Dict[MeasurementType, List[SubsweepGroupPlan]]:
        """
        Create dictionary containing group plans for close and far range measurements.

        - Close range measurement: Add Subsweep group if the user defined starting point is
        effected by the direct leakage.
        - Transition region: Add group plans to bridge the gap between the start of the far range
        measurement region(either end of close range region or user defined start_m) and the
        shortest measurable distance with max_profile, free from direct leakage interference.
        - Add group plan with max_profile. Increase HWAAS as a function of distance to maintain
        SNR throughout the sweep.
        """
        plans = {}

        # Determine shortest direct leakage free distance per profile
        min_dist_m = cls._calc_leakage_free_min_dist(config)

        close_range_transition_m = min_dist_m[a121.Profile.PROFILE_1]

        # Add close range group plan if applicable
        if config.close_range_leakage_cancellation and config.start_m < close_range_transition_m:
            plans[MeasurementType.CLOSE_RANGE] = cls._get_close_range_group_plan(
                close_range_transition_m, config
            )

        # Define transition group plans
        transition_subgroup_plans = cls._get_transition_group_plans(
            config, min_dist_m, MeasurementType.CLOSE_RANGE in plans
        )

        # The number of available subsweeps in the group with max profile.
        num_remaining_subsweeps = cls.NUM_SUBSWEEPS_IN_SENSOR_CONFIG - len(
            transition_subgroup_plans
        )

        # No neighbours if no close range measurement or transition groups defined.
        has_neighboring_subsweep = (
            MeasurementType.CLOSE_RANGE in plans or len(transition_subgroup_plans) != 0
        )

        # Define group plans with max profile
        max_profile_subgroup_plans = cls._get_max_profile_group_plans(
            config, min_dist_m, has_neighboring_subsweep, num_remaining_subsweeps
        )

        far_subgroup_plans = transition_subgroup_plans + max_profile_subgroup_plans

        if len(far_subgroup_plans) != 0:
            plans[MeasurementType.FAR_RANGE] = far_subgroup_plans

        return plans

    @classmethod
    def _get_close_range_group_plan(
        cls, transition_m: float, config: DetectorConfig
    ) -> list[SubsweepGroupPlan]:
        """Define the group plan for close range measurements.

        The close range measurement always use profile 1 to minimize direct leakage region.
        """
        profile = a121.Profile.PROFILE_1
        # Select the end point as the shorter of the user provided end point or the transition
        # point.
        close_range_group_end_m = min(transition_m, config.end_m)
        # No left neighbour as this is the first subsweep when close range measurement is
        # applicable.
        has_neighbour = (False, transition_m < config.end_m)
        return [
            cls._create_group_plan(
                profile,
                config,
                [config.start_m, close_range_group_end_m],
                has_neighbour,
                True,
            )
        ]

    @classmethod
    def _get_transition_group_plans(
        cls,
        config: DetectorConfig,
        min_dist_m: Dict[a121.Profile, float],
        has_close_range_measurement: bool,
    ) -> list[SubsweepGroupPlan]:
        """Define the transition segment group plans.

        The purpose of the transition group is to bridge the gap between the start point of the
        far measurement region and the point where max_profile can be used without interference
        of direct leakage.

        The transition region can consist of maximum two subsweeps, where the first utilize profile
        1 and the second profile 3. Whether both, one or none is used depends on the user provided
        detector config.

        If close_range_leakage_cancellation is set to False, the first group plan should use
        the user provided starting point as start, as there is no close range leakage cancellation
        measurement.
        """
        transition_profiles = [
            profile
            for profile in [a121.Profile.PROFILE_1, a121.Profile.PROFILE_3]
            if profile.value < config.max_profile.value
        ]
        transition_profiles.append(config.max_profile)

        transition_subgroup_plans: list[SubsweepGroupPlan] = []

        for i in range(len(transition_profiles) - 1):
            profile = transition_profiles[i]
            next_profile = transition_profiles[i + 1]

            is_first_group_plan = len(transition_subgroup_plans) == 0
            start_m = None
            if (
                not config.close_range_leakage_cancellation
                and is_first_group_plan
                and config.start_m < min_dist_m[next_profile]
            ):
                start_m = config.start_m

            elif config.start_m < min_dist_m[next_profile] and min_dist_m[profile] < config.end_m:
                start_m = max(min_dist_m[profile], config.start_m)

            if start_m is not None:
                end_m = min(config.end_m, min_dist_m[next_profile])
                has_neighbour = (
                    has_close_range_measurement or not is_first_group_plan,
                    min_dist_m[next_profile] < end_m,
                )

                transition_subgroup_plans.append(
                    cls._create_group_plan(profile, config, [start_m, end_m], has_neighbour, False)
                )

        return transition_subgroup_plans

    @classmethod
    def _get_max_profile_group_plans(
        cls,
        config: DetectorConfig,
        min_dist_m: Dict[a121.Profile, float],
        has_neighboring_subsweep: bool,
        num_remaining_subsweeps: int,
    ) -> list[SubsweepGroupPlan]:
        """Define far range group plans with max_profile

        Divide the measurement range from the shortest leakage free distance of max_profile to
        the end point into equidistance segments and assign HWAAS according to the radar equation
        to maintain SNR throughout the sweep.

        Note, special case when max profile is set to 1 and close range leakage cancellation is not
        used. In this cas, the start of the subsweep is set to the user defined starting point. For
        other max profiles, this is handled in _get_transition_group_plans.
        """

        if min_dist_m[config.max_profile] < config.end_m or (
            not config.close_range_leakage_cancellation
            and config.max_profile == a121.Profile.PROFILE_1
        ):
            if not config.close_range_leakage_cancellation and (
                config.max_profile == a121.Profile.PROFILE_1
            ):
                subsweep_start_m = config.start_m
            else:
                subsweep_start_m = max([config.start_m, min_dist_m[config.max_profile]])

            breakpoints_m = np.linspace(
                subsweep_start_m,
                config.end_m,
                num_remaining_subsweeps + 1,
            ).tolist()

            return [
                cls._create_group_plan(
                    config.max_profile,
                    config,
                    breakpoints_m,
                    (has_neighboring_subsweep, False),
                    False,
                )
            ]
        else:
            return []

    @staticmethod
    def remove_dup(breakpoints: List[int]) -> List[int]:
        unique_bps = sorted(set(breakpoints[1:]))

        unique_bps = [breakpoints[0]] + unique_bps

        return unique_bps

    @classmethod
    def _create_group_plan(
        cls,
        profile: a121.Profile,
        config: DetectorConfig,
        breakpoints_m: list[float],
        has_neighbour: Tuple[bool, bool],
        is_close_range_measurement: bool,
    ) -> SubsweepGroupPlan:
        """Creates a group plan."""
        step_length = cls._limit_step_length(profile, config.max_step_length)
        breakpoints = cls._m_to_points(breakpoints_m, step_length)

        breakpoints = Detector.remove_dup(breakpoints)

        hwaas = cls._calculate_hwaas(
            profile,
            breakpoints,
            config.signal_quality,
            step_length,
            config.reflector_shape,
        )

        extended_breakpoints = cls._add_margin_to_breakpoints(
            profile=profile,
            step_length=step_length,
            base_bpts=breakpoints,
            has_neighbour=has_neighbour,
            config=config,
            is_close_range_measurement=is_close_range_measurement,
        )

        return SubsweepGroupPlan(
            step_length=step_length,
            breakpoints=extended_breakpoints,
            profile=profile,
            hwaas=hwaas,
        )

    @classmethod
    def _calc_leakage_free_min_dist(cls, config: DetectorConfig) -> Dict[a121.Profile, float]:
        """This function calculates the shortest leakage free distance per profile, for all profiles
        up to max_profile"""
        min_dist_m = {}
        for profile, min_dist in cls.MIN_LEAKAGE_FREE_DIST_M.items():
            min_dist_m[profile] = min_dist
            if config.threshold_method == ThresholdMethod.CFAR:
                step_length = cls._limit_step_length(profile, config.max_step_length)
                cfar_margin_m = (
                    Processor.calc_cfar_margin(profile, step_length)
                    * step_length
                    * APPROX_BASE_STEP_LENGTH_M
                )
                min_dist_m[profile] += cfar_margin_m

            if profile == config.max_profile:
                # All profiles up to max_profile has been added. Break and return result.
                break

        return min_dist_m

    @classmethod
    def _calculate_hwaas(
        cls,
        profile: a121.Profile,
        breakpoints: list[int],
        signal_quality: float,
        step_length: int,
        reflector_shape: ReflectorShape,
    ) -> list[int]:
        rlg_per_hwaas = RLG_PER_HWAAS_MAP[profile]
        hwaas = []
        for idx in range(len(breakpoints) - 1):
            processing_gain = calc_processing_gain(profile, step_length)
            subsweep_end_point_m = max(
                APPROX_BASE_STEP_LENGTH_M * breakpoints[idx + 1],
                cls.HWAAS_MIN_DISTANCE,
            )
            rlg = (
                signal_quality
                + reflector_shape.exponent * 10 * np.log10(subsweep_end_point_m)
                - np.log10(processing_gain)
            )
            hwaas_in_subsweep = int(round(10 ** ((rlg - rlg_per_hwaas) / 10)))
            hwaas.append(np.clip(hwaas_in_subsweep, cls.MIN_HWAAS, cls.MAX_HWAAS))
        return hwaas

    @classmethod
    def _add_margin_to_breakpoints(
        cls,
        profile: a121.Profile,
        step_length: int,
        base_bpts: list[int],
        has_neighbour: Tuple[bool, bool],
        config: DetectorConfig,
        is_close_range_measurement: bool,
    ) -> list[int]:
        """
        Add points to segment edges based on their position.

        1. Add one margin to each segment for distance filter initialization
        2. Add an additional margin to segments with neighboring segments for segment overlap
        """

        margin_p = get_distance_filter_edge_margin(profile, step_length) * step_length
        left_margin = margin_p
        right_margin = margin_p

        if has_neighbour[0]:
            left_margin += margin_p

        if has_neighbour[1]:
            right_margin += margin_p

        if config.threshold_method == ThresholdMethod.CFAR and not is_close_range_measurement:
            cfar_margin = Processor.calc_cfar_margin(profile, step_length) * step_length
            left_margin += cfar_margin
            right_margin += cfar_margin

        bpts = copy.copy(base_bpts)
        bpts[0] -= left_margin
        bpts[-1] += right_margin

        return bpts

    @classmethod
    def _limit_step_length(cls, profile: a121.Profile, user_limit: Optional[int]) -> int:
        """
        Calculates step length based on user defined step length and selected profile.

        The step length must yield minimum MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN number of points
        in the span of the FWHM of the envelope.

        If the step length is <24, return the valid step length(defined by
        VALID_STEP_LENGTHS) that is closest to, but not longer than the limit.

        If the limit is 24<=, return the multiple of 24 that is
        closest, but not longer than the limit.
        """

        fwhm_p = ENVELOPE_FWHM_M[profile] / APPROX_BASE_STEP_LENGTH_M
        limit = int(fwhm_p / cls.MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN)

        if user_limit is not None:
            limit = min(user_limit, limit)

        if limit < cls.VALID_STEP_LENGTHS[-1]:
            idx_closest = np.sum(np.array(cls.VALID_STEP_LENGTHS) <= limit) - 1
            return int(cls.VALID_STEP_LENGTHS[idx_closest])
        else:
            return int((limit // cls.VALID_STEP_LENGTHS[-1]) * cls.VALID_STEP_LENGTHS[-1])

    @classmethod
    def _get_max_prf(cls, plans: Dict[MeasurementType, List[SubsweepGroupPlan]]) -> a121.PRF:
        selected_prf = a121.PRF.PRF_19_5_MHz

        if MeasurementType.CLOSE_RANGE in plans:
            (plan,) = plans[MeasurementType.CLOSE_RANGE]
            prf = select_prf(plan.breakpoints[1], plan.profile)
            if prf.frequency < selected_prf.frequency:
                selected_prf = prf

        if MeasurementType.FAR_RANGE in plans:
            subsweep_group_plans = plans[MeasurementType.FAR_RANGE]
            for plan in subsweep_group_plans:
                for bp_idx in range(len(plan.breakpoints) - 1):
                    prf = select_prf(plan.breakpoints[bp_idx + 1], plan.profile)
                    if prf.frequency < selected_prf.frequency:
                        selected_prf = prf

        return selected_prf

    @classmethod
    def _close_subsweep_group_plans_to_sensor_config(
        cls, plan_: List[SubsweepGroupPlan], prf: a121.PRF
    ) -> a121.SensorConfig:
        (plan,) = plan_
        subsweeps = []
        subsweeps.append(
            a121.SubsweepConfig(
                start_point=0,
                num_points=1,
                step_length=1,
                profile=a121.Profile.PROFILE_4,
                hwaas=plan.hwaas[0],
                receiver_gain=15,
                phase_enhancement=True,
                enable_loopback=True,
                prf=a121.PRF.PRF_15_6_MHz,
            )
        )
        num_points = int((plan.breakpoints[1] - plan.breakpoints[0]) / plan.step_length)
        subsweeps.append(
            a121.SubsweepConfig(
                start_point=plan.breakpoints[0],
                num_points=num_points,
                step_length=plan.step_length,
                profile=plan.profile,
                hwaas=plan.hwaas[0],
                receiver_gain=5,
                phase_enhancement=True,
                prf=prf,
            )
        )
        return a121.SensorConfig(subsweeps=subsweeps, sweeps_per_frame=10)

    @classmethod
    def _far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
        cls, subsweep_group_plans: list[SubsweepGroupPlan], prf: a121.PRF
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
                        hwaas=plan.hwaas[bp_idx],
                        receiver_gain=10,
                        phase_enhancement=True,
                        prf=prf,
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
        start_point_m = bpts_m[0]
        start_point_p = int(start_point_m / APPROX_BASE_STEP_LENGTH_M)

        breakpoint_offsets_p_fractional = (bpts_m - start_point_m) / APPROX_BASE_STEP_LENGTH_M
        breakpoints_p_fractional = breakpoint_offsets_p_fractional + start_point_p

        return (  # type: ignore[no-any-return]
            ((np.round(breakpoints_p_fractional) // step_length) * step_length)
            .astype(int)
            .tolist()
        )

    def _add_context_to_processor_spec(self) -> dict[int, list[ProcessorSpec]]:
        """
        Create and add processor context to processor specification.
        """

        updated_specs_all_sensors = {}
        for sensor_id in self.context.sensor_ids:
            assert self.context.noise_calibration is not None
            bg_noise_stds = self.context.noise_calibration.bg_noise_std(
                sensor_id, self.processor_specs, self.session_config
            )
            updated_specs: List[ProcessorSpec] = []

            if self.context.recorded_threshold_calibration is not None:
                recorded_thresholds_mean_sweep = (
                    self.context.recorded_threshold_calibration.recorded_thresholds_mean_sweep(
                        sensor_id,
                        self.processor_specs,
                        self.session_config,
                        self.context.noise_calibration,
                        self.context.close_range_calibration,
                    )
                )
                recorded_thresholds_noise_std = (
                    self.context.recorded_threshold_calibration.recorded_thresholds_noise_std(
                        sensor_id,
                        self.processor_specs,
                        self.session_config,
                        self.context.noise_calibration,
                        self.context.close_range_calibration,
                    )
                )
            else:
                recorded_thresholds_mean_sweep = None
                recorded_thresholds_noise_std = None

            for idx, (spec, bg_noise_std) in enumerate(zip(self.processor_specs, bg_noise_stds)):
                if (
                    recorded_thresholds_mean_sweep is not None
                    and recorded_thresholds_noise_std is not None
                ):
                    recorded_threshold_mean_sweep = recorded_thresholds_mean_sweep[idx]
                    recorded_threshold_noise_std = recorded_thresholds_noise_std[idx]
                else:
                    recorded_threshold_mean_sweep = None
                    recorded_threshold_noise_std = None

                if self.context.close_range_calibration is not None:
                    direct_leakage = self.context.close_range_calibration.direct_leakage(
                        sensor_id,
                        self.processor_specs,
                        self.session_config,
                    )
                    phase_jitter_comp_ref = (
                        self.context.close_range_calibration.phase_jitter_comp_reference(
                            sensor_id,
                            self.processor_specs,
                            self.session_config,
                        )
                    )
                else:
                    direct_leakage = None
                    phase_jitter_comp_ref = None

                if self.context.offset_calibration is not None:
                    loopback_peak_location_m = (
                        self.context.offset_calibration.loopback_peak_location_m(sensor_id)
                    )
                else:
                    loopback_peak_location_m = None

                if self.context.recorded_threshold_calibration is not None:
                    reference_temperature = (
                        self.context.recorded_threshold_calibration.reference_temperature(
                            sensor_id,
                            self.processor_specs,
                            self.session_config,
                            self.context.noise_calibration,
                            self.context.close_range_calibration,
                        )
                    )
                else:
                    reference_temperature = None

                processor_context = ProcessorContext(
                    recorded_threshold_mean_sweep=recorded_threshold_mean_sweep,
                    recorded_threshold_noise_std=recorded_threshold_noise_std,
                    bg_noise_std=bg_noise_std,
                    direct_leakage=direct_leakage,
                    phase_jitter_comp_ref=phase_jitter_comp_ref,
                    reference_temperature=reference_temperature,
                    loopback_peak_location_m=loopback_peak_location_m,
                )
                updated_specs.append(attrs.evolve(spec, processor_context=processor_context))
            updated_specs_all_sensors[sensor_id] = updated_specs
        return updated_specs_all_sensors


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_ids: list[int],
    config: DetectorConfig,
    context: DetectorContext,
) -> None:
    algo_group.create_dataset(
        "sensor_ids",
        data=sensor_ids,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "detector_config", config.to_json())

    context_group = algo_group.create_group("context")
    opser.serialize(context, context_group)


def _load_algo_data(
    algo_group: h5py.Group,
) -> Tuple[list[int], DetectorConfig, DetectorContext]:
    sensor_ids = algo_group["sensor_ids"][()].tolist()
    try:
        config = detector_config_timeline.migrate(algo_group["detector_config"][()].decode())
    except tm.core.MigrationErrorGroup as exc:
        msg = ""
        match = exc.subgroup(BadMigrationPathError)
        if match is not None:
            # Add more details from exception thrown
            for exc_arg in match.exceptions[0].args:
                if isinstance(exc_arg, str):
                    print(exc_arg)
                    msg += f", {exc_arg}"

        raise TypeError(msg) from exc

    context_group = algo_group["context"]
    context = detector_context_timeline.migrate(context_group)

    return sensor_ids, config, context


@attrs.mutable
@attrs.mutable(kw_only=True)
class _DetectorConfig_v0(AlgoConfigBase):
    start_m: float = attrs.field(default=0.25)
    end_m: float = attrs.field(default=3.0)
    max_step_length: Optional[int] = attrs.field(default=None)
    max_profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_5, converter=a121.Profile)
    close_range_leakage_cancellation: bool = attrs.field(default=False)
    signal_quality: float = attrs.field(default=15.0)
    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR,
        converter=ThresholdMethod,
    )
    peaksorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.STRONGEST,
        converter=PeakSortingMethod,
    )
    reflector_shape: ReflectorShape = attrs.field(
        default=ReflectorShape.GENERIC,
        converter=ReflectorShape,
    )
    num_frames_in_recorded_threshold: int = attrs.field(default=100)
    fixed_threshold_value: float = attrs.field(default=DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE)
    fixed_strength_threshold_value: float = attrs.field(
        default=DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE
    )
    threshold_sensitivity: float = attrs.field(default=DEFAULT_THRESHOLD_SENSITIVITY)
    update_rate: Optional[float] = attrs.field(default=50.0)
    prf: Optional[a121.PRF] = attrs.field(default=None)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return []


class BadMigrationPathError(Exception): ...


def always_raise_an_error_when_migrating_v0(_: _DetectorConfig_v0) -> DetectorConfig:
    msg = f"Try opening the file in an earlier version of ET <= {PRF_REMOVED_ET_VERSION}"
    raise BadMigrationPathError(msg)


detector_config_timeline = (
    tm.start(_DetectorConfig_v0)
    .load(str, _DetectorConfig_v0.from_json, fail=[TypeError])
    .nop()
    .epoch(DetectorConfig, always_raise_an_error_when_migrating_v0, fail=[BadMigrationPathError])
    .load(str, DetectorConfig.from_json, fail=[TypeError])
)
