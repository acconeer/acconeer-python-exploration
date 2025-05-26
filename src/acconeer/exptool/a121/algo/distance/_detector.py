# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

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
from acconeer.exptool.a121._core.entities.configs.sensor_config import (
    VALIDATION_TAG_BUFFER_SIZE_TOO_LARGE,
)
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    AlgoConfigBase,
    Controller,
    PeakSortingMethod,
    ReflectorShape,
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
    ProcessorContext,
    ProcessorResult,
    ThresholdMethod,
)
from ._translation import (
    detector_config_to_processor_specs,
    detector_config_to_session_config,
    get_num_far_subsweeps,
)


class ConfigMismatchError(RuntimeError):
    pass


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

        session_config = detector_config_to_session_config(self, [1])
        if any(
            sc_val_res.tag is VALIDATION_TAG_BUFFER_SIZE_TOO_LARGE
            for sc_val_res in session_config._collect_validation_results()
        ):
            error_msg_stem = "Required buffer size is too large. "
            validation_results.append(
                a121.ValidationError(
                    self,
                    "end_m",
                    error_msg_stem + "Try decreasing the range.",
                )
            )
            validation_results.append(
                a121.ValidationError(
                    self,
                    "start_m",
                    error_msg_stem + "Try decreasing the range.",
                )
            )
            validation_results.append(
                a121.ValidationError(
                    self,
                    "max_step_length",
                    (
                        error_msg_stem
                        + "Allowing a higher step length will require a smaller buffer."
                    ),
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

        session_config = detector_config_to_session_config(config=config, sensor_ids=sensor_ids)

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
    def _has_close_range_measurement(cls, config: DetectorConfig) -> bool:
        # sensor_ids=[1] as the detector is running the same config for all sensors.
        session_config = detector_config_to_session_config(config, sensor_ids=[1])
        num_far_subsweeps = get_num_far_subsweeps(session_config, config)
        specs = detector_config_to_processor_specs(
            config=config, sensor_ids=[1], num_far_subsweeps=num_far_subsweeps
        )
        return MeasurementType.CLOSE_RANGE in [
            spec.processor_config.measurement_type for spec in specs
        ]

    @classmethod
    def _has_recorded_threshold_mode(cls, config: DetectorConfig, sensor_ids: list[int]) -> bool:
        processor_specs = detector_config_to_processor_specs(
            config=config,
            sensor_ids=sensor_ids,
            # num_far_subsweeps hardcoded as it does not impact the threshold method.
            num_far_subsweeps=4,
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
            if status.detector_state.name == DetailedStatus.CONFIG_MISMATCH.name:
                raise ConfigMismatchError(msg)
            else:
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
        self.session_config = detector_config_to_session_config(config, self.sensor_ids)
        num_far_subsweeps = get_num_far_subsweeps(self.session_config, config)
        self.processor_specs = detector_config_to_processor_specs(
            config, self.sensor_ids, num_far_subsweeps
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

    def stop_recorder(self) -> Any:
        """Stop the recorder if the detector session is already stopped"""
        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()

        return recorder_result

    def stop_detector(self) -> Any:
        """Stops only the detector session."""
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        self.client.stop_session()
        self.started = False
        return None

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
