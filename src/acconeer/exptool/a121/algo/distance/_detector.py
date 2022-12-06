# Copyright (c) Acconeer AB, 2022
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

from acconeer.exptool import a121
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    AlgoBase,
    AlgoConfigBase,
    get_distance_filter_edge_margin,
    select_prf,
)

from ._aggregator import Aggregator, AggregatorConfig, PeakSortingMethod, ProcessorSpec
from ._processors import (
    DEFAULT_FIXED_THRESHOLD_VALUE,
    DEFAULT_THRESHOLD_SENSITIVITY,
    MeasurementType,
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorMode,
    ProcessorResult,
    ThresholdMethod,
    calculate_bg_noise_std,
    calculate_loopback_peak_location,
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
    INVALID_DETECTOR_CONFIG_RANGE = enum.auto()


@attrs.frozen(kw_only=True)
class SubsweepGroupPlan:
    step_length: int = attrs.field()
    breakpoints: list[int] = attrs.field()
    profile: a121.Profile = attrs.field()
    hwaas: list[int] = attrs.field()


Plan = Dict[MeasurementType, List[SubsweepGroupPlan]]


@attrs.mutable(kw_only=True)
class DetectorContext(AlgoBase):
    single_sensor_contexts: Dict[int, SingleSensorContext] = attrs.field(default=None)
    _GROUP_NAME = "sensor_id_"

    @property
    def sensor_ids(self) -> Optional[list[int]]:
        if self.single_sensor_contexts:
            return list(self.single_sensor_contexts.keys())
        else:
            return None

    def to_h5(self, group: h5py.Group) -> None:
        if self.single_sensor_contexts is not None:
            for sensor_id, context in self.single_sensor_contexts.items():
                context.to_h5(group.create_group(self._GROUP_NAME + str(sensor_id)))

    @classmethod
    def from_h5(cls, group: h5py.Group) -> DetectorContext:
        context_dict = {}

        for key in group.keys():
            if cls._GROUP_NAME in key:
                sensor_id = int(key.split("_")[-1])
                context_dict[sensor_id] = SingleSensorContext.from_h5(group[key])

        return DetectorContext(single_sensor_contexts=context_dict)


@attrs.mutable(kw_only=True)
class SingleSensorContext(AlgoBase):
    loopback_peak_location_m: Optional[float] = attrs.field(default=None)
    direct_leakage: Optional[npt.NDArray[np.complex_]] = attrs.field(default=None)
    phase_jitter_comp_reference: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    recorded_thresholds_mean_sweep: Optional[List[npt.NDArray[np.float_]]] = attrs.field(
        default=None
    )
    recorded_thresholds_noise_std: Optional[List[List[np.float_]]] = attrs.field(default=None)
    bg_noise_std: Optional[List[List[float]]] = attrs.field(default=None)
    session_config_used_during_calibration: Optional[a121.SessionConfig] = attrs.field(
        default=None
    )
    reference_temperature: Optional[int] = attrs.field(default=None)
    sensor_calibration: Optional[a121.SensorCalibration] = attrs.field(default=None)
    # TODO: Make recorded_thresholds Optional[List[Optional[npt.NDArray[np.float_]]]]

    def to_h5(self, group: h5py.Group) -> None:
        for k, v in attrs.asdict(self, recurse=False).items():
            if k in [
                "recorded_thresholds_mean_sweep",
                "recorded_thresholds_noise_std",
                "bg_noise_std",
            ]:
                continue

            if v is None:
                continue

            if isinstance(v, a121.SessionConfig):
                _create_h5_string_dataset(group, k, v.to_json())
            elif isinstance(v, a121.SensorCalibration):
                sensor_calibration_group = group.create_group("sensor_calibration")
                v.to_h5(sensor_calibration_group)
            elif isinstance(v, np.ndarray) or isinstance(v, float) or isinstance(v, int):
                group.create_dataset(k, data=v, track_times=False)
            else:
                raise RuntimeError(
                    f"Unexpected {type(self).__name__} field '{k}' of type '{type(v)}'"
                )

        if self.recorded_thresholds_mean_sweep is not None:
            recorded_thresholds_mean_sweep_group = group.create_group(
                "recorded_thresholds_mean_sweep"
            )

            for i, v in enumerate(self.recorded_thresholds_mean_sweep):
                recorded_thresholds_mean_sweep_group.create_dataset(
                    f"index_{i}", data=v, track_times=False
                )

        if self.recorded_thresholds_noise_std is not None:
            recorded_thresholds_std_group = group.create_group("recorded_thresholds_noise_std")

            for i, v in enumerate(self.recorded_thresholds_noise_std):
                recorded_thresholds_std_group.create_dataset(
                    f"index_{i}", data=v, track_times=False
                )

        if self.bg_noise_std is not None:
            bg_noise_std_group = group.create_group("bg_noise_std")

            for i, v in enumerate(self.bg_noise_std):
                bg_noise_std_group.create_dataset(f"index_{i}", data=v, track_times=False)

    @classmethod
    def from_h5(cls, group: h5py.Group) -> SingleSensorContext:
        context_dict = {}

        unknown_keys = set(group.keys()) - set(attrs.fields_dict(SingleSensorContext).keys())
        if unknown_keys:
            raise Exception(f"Unknown field(s) in stored context: {unknown_keys}")

        field_map = {
            "loopback_peak_location_m": None,
            "direct_leakage": None,
            "reference_temperature": None,
            "phase_jitter_comp_reference": None,
            "session_config_used_during_calibration": a121.SessionConfig.from_json,
        }
        for k, func in field_map.items():
            try:
                v = group[k][()]
            except KeyError:
                continue

            context_dict[k] = func(v) if func else v

        if "recorded_thresholds_mean_sweep" in group:
            mean_sweeps = _get_group_items(group["recorded_thresholds_mean_sweep"])
            context_dict["recorded_thresholds_mean_sweep"] = mean_sweeps

        if "recorded_thresholds_noise_std" in group:
            noise_stds = _get_group_items(group["recorded_thresholds_noise_std"])
            context_dict["recorded_thresholds_noise_std"] = noise_stds

        if "bg_noise_std" in group:
            bg_noise_std = _get_group_items(group["bg_noise_std"])
            context_dict["bg_noise_std"] = bg_noise_std

        if "sensor_calibration" in group:
            context_dict["sensor_calibration"] = a121.SensorCalibration.from_h5(
                group["sensor_calibration"]
            )

        return SingleSensorContext(**context_dict)


@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=0.25)
    """Start point of measurement interval in meters."""

    end_m: float = attrs.field(default=3.0)
    """End point of measurement interval in meters."""

    max_step_length: Optional[int] = attrs.field(default=None)  # TODO: Check validity
    """Used to limit step length. If no argument is provided, the step length is automatically
    calculated based on the profile."""

    max_profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_5, converter=a121.Profile)
    """Specifies the longest allowed profile. If no argument is provided, the highest possible
    profile without interference of direct leakage is used to maximize SNR."""

    signal_quality: float = attrs.field(default=15.0)
    """Signal quality. High quality equals higher HWAAS and better SNR but increase power
    consumption."""

    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR,
        converter=ThresholdMethod,
    )
    """Threshold method"""

    peaksorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.HIGHEST_RCS,
        converter=PeakSortingMethod,
    )
    """Sorting method of estimated distances."""

    num_frames_in_recorded_threshold: int = attrs.field(default=100)
    """Number of frames used when calibrating threshold."""

    fixed_threshold_value: float = attrs.field(default=DEFAULT_FIXED_THRESHOLD_VALUE)
    """Value of fixed threshold."""

    threshold_sensitivity: float = attrs.field(default=DEFAULT_THRESHOLD_SENSITIVITY)
    """Sensitivity of threshold. High sensitivity equals low detection threshold, low sensitivity
    equals high detection threshold."""

    update_rate: Optional[float] = attrs.field(default=50.0)
    """Sets the detector update rate."""

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

        return validation_results


@attrs.frozen(kw_only=True)
class DetectorResult:
    rcs: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    distances: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    processor_results: list[ProcessorResult] = attrs.field()
    service_extended_result: list[dict[int, a121.Result]] = attrs.field()


class Detector:
    """Distance detector
    :param client: Client
    :param sensor_id: Sensor id
    :param detector_config: Detector configuration
    :param context: Detector context
    """

    MIN_DIST_M = 0.0
    MAX_DIST_M = 17.0
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
        client: a121.ClientBase,
        sensor_ids: list[int],
        detector_config: DetectorConfig,
        context: Optional[DetectorContext] = None,
    ) -> None:
        self.client = client
        self.sensor_ids = sensor_ids
        self.detector_config = detector_config
        self.started = False

        if context is None or not bool(context.single_sensor_contexts):
            self.context = DetectorContext(
                single_sensor_contexts={
                    sensor_id: SingleSensorContext() for sensor_id in self.sensor_ids
                }
            )
        else:
            self.context = context

        self.aggregator: Optional[Aggregator] = None

        self.update_config(self.detector_config)

    def _validate_ready_for_calibration(self) -> None:
        if self.started:
            raise RuntimeError("Already started")
        if self.processor_specs is None:
            raise ValueError("Processor specification not defined")
        if self.session_config is None:
            raise ValueError("Session config not defined")

    def calibrate_detector(self) -> None:
        """Run the required detector calibration routines, based on the detector config."""

        self._validate_ready_for_calibration()

        self._calibrate_offset()

        self._calibrate_noise()

        if self._has_close_range_measurement(self.detector_config):
            self._calibrate_close_range()

        if self._has_close_range_measurement(
            self.detector_config
        ) or self._has_recorded_threshold_mode(self.detector_config, self.sensor_ids):
            self._record_threshold()

        for context in self.context.single_sensor_contexts.values():
            context.session_config_used_during_calibration = self.session_config

    def _calibrate_close_range(self) -> None:
        """Calibrates the close range measurement parameters used when subtracting the direct
        leakage from the measured signal.

        The parameters calibrated are the direct leakage and a phase reference, used to reduce
        the amount of phase jitter, with the purpose of reducing the residual.
        """

        close_range_spec = self._filter_close_range_spec(self.processor_specs)
        spec = self._update_processor_mode(close_range_spec, ProcessorMode.LEAKAGE_CALIBRATION)

        # Note - Setup with full session_config to match the structure of spec
        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)

        aggregators = {
            sensor_id: Aggregator(
                session_config=self.session_config,
                extended_metadata=extended_metadata,
                config=AggregatorConfig(),
                specs=spec,
                sensor_id=sensor_id,
            )
            for sensor_id in self.sensor_ids
        }

        self.client.start_session()
        extended_result = self.client.get_next()
        assert isinstance(extended_result, list)
        self.client.stop_session()

        for sensor_id, context in self.context.single_sensor_contexts.items():
            aggregator_result = aggregators[sensor_id].process(extended_result=extended_result)
            (processor_result,) = aggregator_result.processor_results
            assert processor_result.phase_jitter_comp_reference is not None

            context.direct_leakage = processor_result.direct_leakage
            context.phase_jitter_comp_reference = processor_result.phase_jitter_comp_reference
            context.recorded_thresholds_mean_sweep = None
            context.recorded_thresholds_noise_std = None

            context.sensor_calibration = self.client.calibrations[sensor_id]

    def _record_threshold(self) -> None:
        """Calibrates the parameters used when forming the recorded threshold."""

        # TODO: Ignore/override threshold method while recording threshold

        specs_updated = self._update_processor_mode(
            self.processor_specs, ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
        )

        specs = self._add_context_to_processor_spec(specs_updated)

        extended_metadata = self.client.setup_session(self.session_config)
        assert isinstance(extended_metadata, list)
        aggregators = {
            sensor_id: Aggregator(
                session_config=self.session_config,
                extended_metadata=extended_metadata,
                config=AggregatorConfig(),
                specs=specs[sensor_id],
                sensor_id=sensor_id,
            )
            for sensor_id in self.sensor_ids
        }

        self.client.start_session()
        aggregators_result = {}
        for _ in range(self.detector_config.num_frames_in_recorded_threshold):
            extended_result = self.client.get_next()
            assert isinstance(extended_result, list)
            aggregators_result = {
                sensor_id: aggregators[sensor_id].process(extended_result=extended_result)
                for sensor_id in self.sensor_ids
            }
        self.client.stop_session()

        assert isinstance(extended_result, list)

        for sensor_id, context in self.context.single_sensor_contexts.items():
            recorded_thresholds_mean_sweep = []
            recorded_thresholds_noise_std = []
            for processor_result in aggregators_result[sensor_id].processor_results:
                # Since we know what mode the processor is running in
                assert processor_result.recorded_threshold_mean_sweep is not None
                assert processor_result.recorded_threshold_noise_std is not None

                recorded_thresholds_mean_sweep.append(
                    processor_result.recorded_threshold_mean_sweep
                )
                recorded_thresholds_noise_std.append(processor_result.recorded_threshold_noise_std)

            context.recorded_thresholds_mean_sweep = recorded_thresholds_mean_sweep
            context.recorded_thresholds_noise_std = recorded_thresholds_noise_std
            # Grab temperature from first group as it is the same for all.
            context.reference_temperature = extended_result[0][sensor_id].temperature

    def _calibrate_noise(self) -> None:
        """Estimates the standard deviation of the noise in each subsweep by setting enable_tx to
        False and collecting data, used to calculate the deviation.

        The calibration procedure can be done at any time as it is performed with Tx off, and is
        not effected by objects in front of the sensor.

        This function is called from the start() in the case of CFAR and Fixed threshold and from
        record_threshold() in the case of Recorded threshold. The reason for calling from
        record_threshold() is that it is used when calculating the threshold.
        """

        session_config = copy.deepcopy(self.session_config)

        for sensor_id in self.sensor_ids:
            for group in session_config.groups:
                group[sensor_id].sweeps_per_frame = 1
                for subsweep in group[sensor_id].subsweeps:
                    subsweep.enable_tx = False
                    subsweep.step_length = 1
                    subsweep.start_point = 0
                    # Set num_points to a high number to get sufficient number of data points to
                    # estimate the standard deviation.
                    subsweep.num_points = 500

        extended_metadata = self.client.setup_session(session_config)
        assert isinstance(extended_metadata, list)

        self.client.start_session()
        extended_result = self.client.get_next()
        assert isinstance(extended_result, list)
        self.client.stop_session()

        for sensor_id, context in self.context.single_sensor_contexts.items():
            bg_noise_one_sensor = []
            for spec in self.processor_specs:
                result = extended_result[spec.group_index][sensor_id]
                sensor_config = self.session_config.groups[spec.group_index][sensor_id]
                subsweep_configs = sensor_config.subsweeps
                bg_noise_std_in_subsweep = []
                for idx in spec.subsweep_indexes:
                    if not subsweep_configs[idx].enable_loopback:
                        subframe = result.subframes[idx]
                        subsweep_std = calculate_bg_noise_std(subframe, subsweep_configs[idx])
                        bg_noise_std_in_subsweep.append(subsweep_std)
                bg_noise_one_sensor.append(bg_noise_std_in_subsweep)
            context.bg_noise_std = bg_noise_one_sensor

    def _calibrate_offset(self) -> None:
        """Estimates sensor offset error based on loopback measurement."""

        self._validate_ready_for_calibration()

        sensor_config = a121.SensorConfig(
            start_point=-30,
            num_points=50,
            step_length=1,
            profile=a121.Profile.PROFILE_1,
            hwaas=64,
            sweeps_per_frame=1,
            enable_loopback=True,
            phase_enhancement=True,
        )

        session_config = a121.SessionConfig(
            {sensor_id: sensor_config for sensor_id in self.sensor_ids}, extended=True
        )
        self.client.setup_session(session_config)
        self.client.start_session()
        extended_result = self.client.get_next()
        self.client.stop_session()

        assert isinstance(extended_result, list)

        for sensor_id, context in self.context.single_sensor_contexts.items():
            context.loopback_peak_location_m = calculate_loopback_peak_location(
                extended_result[0][sensor_id], sensor_config
            )

    @staticmethod
    def _get_sensor_calibrations(context: DetectorContext) -> dict[int, a121.SensorCalibration]:
        return {
            sensor_id: single_context.sensor_calibration
            for sensor_id, single_context in context.single_sensor_contexts.items()
            if single_context.sensor_calibration is not None
        }

    @classmethod
    def get_detector_status(
        cls,
        config: DetectorConfig,
        context: DetectorContext,
        sensor_ids: list[int],
    ) -> DetectorStatus:
        """Returns the detector status along with the detector state."""

        if not cls._valid_detector_config_range(config=config):
            return DetectorStatus(
                detector_state=DetailedStatus.INVALID_DETECTOR_CONFIG_RANGE,
                ready_to_start=False,
            )

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

        if context.single_sensor_contexts is None:
            return DetectorStatus(
                detector_state=DetailedStatus.CONTEXT_MISSING,
                ready_to_start=False,
            )

        (session_config, _,) = cls._detector_to_session_config_and_processor_specs(
            config=config, sensor_ids=sensor_ids
        )

        # Offset calibration is always performed as a part of the detector calibration process.
        # Use this as indication whether detector calibration has been performed.
        calibration_missing = np.any(
            [
                ctx.loopback_peak_location_m is None
                for ctx in context.single_sensor_contexts.values()
            ]
        )
        config_mismatch = np.any(
            [
                ctx.session_config_used_during_calibration != session_config
                for ctx in context.single_sensor_contexts.values()
            ]
        )

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

    @classmethod
    def _valid_detector_config_range(cls, config: DetectorConfig) -> bool:
        return cls.MIN_DIST_M <= config.start_m and config.end_m <= cls.MAX_DIST_M

    @staticmethod
    def _close_range_calibrated(context: DetectorContext) -> bool:
        has_dl = np.all(
            [ctx.direct_leakage is not None for ctx in context.single_sensor_contexts.values()]
        )
        has_pjcr = np.all(
            [
                ctx.phase_jitter_comp_reference is not None
                for ctx in context.single_sensor_contexts.values()
            ]
        )

        if has_dl != has_pjcr:
            raise RuntimeError

        return bool(has_dl and has_pjcr)

    @staticmethod
    def _recorded_threshold_calibrated(context: DetectorContext) -> bool:
        mean_sweep_calibrated = np.all(
            [
                ctx.recorded_thresholds_mean_sweep is not None
                for ctx in context.single_sensor_contexts.values()
            ]
        )

        std_calibrated = np.all(
            [
                ctx.recorded_thresholds_noise_std is not None
                for ctx in context.single_sensor_contexts.values()
            ]
        )

        return bool(mean_sweep_calibrated and std_calibrated)

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
        (_, processor_specs,) = self._detector_to_session_config_and_processor_specs(
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
            raise RuntimeError("Already started")

        status = self.get_detector_status(self.detector_config, self.context, self.sensor_ids)

        if not status.ready_to_start:
            raise RuntimeError(f"Not ready to start ({status.detector_state.name})")
        specs = self._add_context_to_processor_spec(self.processor_specs)

        sensor_calibration = self._get_sensor_calibrations(self.context)

        extended_metadata = self.client.setup_session(
            self.session_config, calibrations=sensor_calibration
        )

        assert isinstance(extended_metadata, list)
        assert np.all(
            [
                context.loopback_peak_location_m is not None
                for context in self.context.single_sensor_contexts.values()
            ]
        )
        aggregator_config = AggregatorConfig(
            peak_sorting_method=self.detector_config.peaksorting_method
        )
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
                    self.detector_config,
                    self.context,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        self.client.start_session(recorder)
        self.started = True

    def get_next(self) -> Dict[int, DetectorResult]:
        """Called from host to get next measurement."""
        if not self.started:
            raise RuntimeError("Not started")

        assert self.aggregators is not None

        extended_result = self.client.get_next()
        assert isinstance(extended_result, list)

        aggregator_results = {
            sensor_id: self.aggregators[sensor_id].process(extended_result=extended_result)
            for sensor_id in self.sensor_ids
        }

        result = {
            sensor_id: DetectorResult(
                rcs=aggregator_results[sensor_id].estimated_rcs,
                distances=aggregator_results[sensor_id].estimated_distances,
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
            raise RuntimeError("Already stopped")

        recorder_result = self.client.stop_session()

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

        if MeasurementType.CLOSE_RANGE in plans:
            sensor_config = cls._close_subsweep_group_plans_to_sensor_config(
                plans[MeasurementType.CLOSE_RANGE]
            )
            groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})
            processor_specs.append(
                ProcessorSpec(
                    processor_config=ProcessorConfig(
                        threshold_method=ThresholdMethod.RECORDED,
                        measurement_type=MeasurementType.CLOSE_RANGE,
                        threshold_sensitivity=config.threshold_sensitivity,
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
                plans[MeasurementType.FAR_RANGE]
            )
            groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})

            processor_config = ProcessorConfig(
                threshold_method=config.threshold_method,
                fixed_threshold_value=config.fixed_threshold_value,
                threshold_sensitivity=config.threshold_sensitivity,
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
        if config.start_m < close_range_transition_m:
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
        has_neighbouring_subsweep = (
            MeasurementType.CLOSE_RANGE in plans or len(transition_subgroup_plans) != 0
        )

        # Define group plans with max profile
        max_profile_subgroup_plans = cls._get_max_profile_group_plans(
            config, min_dist_m, has_neighbouring_subsweep, num_remaining_subsweeps
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
        # No left neighbour as this is the first subsweep when close range measurement is
        # applicable.
        has_neighbour = (False, transition_m < config.end_m)
        return [
            cls._create_group_plan(
                profile, config, [config.start_m, transition_m], has_neighbour, True
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
        """
        transition_profiles = [
            profile
            for profile in [a121.Profile.PROFILE_1, a121.Profile.PROFILE_3]
            if profile.value < config.max_profile.value
        ]
        transition_profiles.append(config.max_profile)

        transition_subgroup_plans: list = []

        for i in range(len(transition_profiles) - 1):
            profile = transition_profiles[i]
            next_profile = transition_profiles[i + 1]

            if config.start_m < min_dist_m[next_profile] and min_dist_m[profile] < config.end_m:
                start_m = max(min_dist_m[profile], config.start_m)
                end_m = min(config.end_m, min_dist_m[next_profile])
                has_neighbour = (
                    has_close_range_measurement or len(transition_subgroup_plans) != 0,
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
        has_neighbouring_subsweep: bool,
        num_remaining_subsweeps: int,
    ) -> list[SubsweepGroupPlan]:
        """Define far range group plans with max_profile

        Divide the measurement range from the shortest leakage free distance of max_profile to
        the end point into equidistance segments and assign HWAAS according to the radar equation
        to maintain SNR throughout the sweep.
        """

        if min_dist_m[config.max_profile] < config.end_m:
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
                    (has_neighbouring_subsweep, False),
                    False,
                )
            ]
        else:
            return []

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
        hwaas = cls._calculate_hwaas(profile, breakpoints, config.signal_quality, step_length)

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
        cls, profile: a121.Profile, breakpoints: list[int], signal_quality: float, step_length: int
    ) -> list[int]:
        rlg_per_hwaas = Aggregator.RLG_PER_HWAAS_MAP[profile]
        hwaas = []
        for idx in range(len(breakpoints) - 1):
            processing_gain = Aggregator.calc_processing_gain(profile, step_length)
            subsweep_end_point_m = max(
                APPROX_BASE_STEP_LENGTH_M * breakpoints[idx + 1],
                cls.HWAAS_MIN_DISTANCE,
            )
            rlg = signal_quality + 40 * np.log10(subsweep_end_point_m) - np.log10(processing_gain)
            hwaas_in_subsweep = int(10 ** ((rlg - rlg_per_hwaas) / 10))
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
        2. Add an additional margin to segments with neighbouring segments for segment overlap
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
                hwaas=plan.hwaas[0],
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
                hwaas=plan.hwaas[0],
                receiver_gain=5,
                phase_enhancement=True,
                prf=select_prf(plan.breakpoints[1], plan.profile),
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
                        hwaas=plan.hwaas[bp_idx],
                        receiver_gain=10,
                        phase_enhancement=True,
                        prf=select_prf(plan.breakpoints[bp_idx + 1], plan.profile),
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
        start_point = int(bpts_m[0] / APPROX_BASE_STEP_LENGTH_M)
        num_steps = (bpts_m[-1] - bpts_m[0]) / (APPROX_BASE_STEP_LENGTH_M)
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
    ) -> dict[int, list[ProcessorSpec]]:
        """
        Create and add processor context to processor specification.
        """

        updated_specs_all_sensors = {}
        for sensor_id, context in self.context.single_sensor_contexts.items():
            assert context.bg_noise_std is not None
            updated_specs: List[ProcessorSpec] = []
            for idx, (spec, bg_noise_std) in enumerate(zip(processor_specs, context.bg_noise_std)):
                if (
                    context.recorded_thresholds_mean_sweep is not None
                    or context.recorded_thresholds_noise_std is not None
                ):
                    assert context.recorded_thresholds_mean_sweep is not None
                    assert context.recorded_thresholds_noise_std is not None
                    recorded_thresholds_mean_sweep = context.recorded_thresholds_mean_sweep[idx]
                    recorded_threshold_noise_std = context.recorded_thresholds_noise_std[idx]
                else:
                    recorded_thresholds_mean_sweep = None
                    recorded_threshold_noise_std = None

                if (
                    context.direct_leakage is not None
                    or context.phase_jitter_comp_reference is not None
                ):
                    direct_leakage = context.direct_leakage
                    phase_jitter_comp_ref = context.phase_jitter_comp_reference
                else:
                    direct_leakage = None
                    phase_jitter_comp_ref = None

                if context.loopback_peak_location_m is not None:
                    loopback_peak_location_m = context.loopback_peak_location_m
                else:
                    loopback_peak_location_m = None

                if context.reference_temperature is not None:
                    reference_temperature = context.reference_temperature
                else:
                    reference_temperature = None

                processor_context = ProcessorContext(
                    recorded_threshold_mean_sweep=recorded_thresholds_mean_sweep,
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
    detector_config: DetectorConfig,
    context: DetectorContext,
) -> None:
    algo_group.create_dataset(
        "sensor_ids",
        data=sensor_ids,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "detector_config", detector_config.to_json())

    context_group = algo_group.create_group("context")
    context.to_h5(context_group)


def _load_algo_data(
    algo_group: h5py.Group,
) -> Tuple[int, DetectorConfig, DetectorContext]:
    sensor_id = algo_group["sensor_ids"][()]
    config = DetectorConfig.from_json(algo_group["detector_config"][()])

    context_group = algo_group["context"]
    context = DetectorContext.from_h5(context_group)

    return sensor_id, config, context


def _get_group_items(group: h5py.Group) -> list[npt.NDArray]:
    group_items = []

    i = 0
    while True:
        try:
            v = group[f"index_{i}"][()]
        except KeyError:
            break

        group_items.append(v)
        i += 1
    return group_items
