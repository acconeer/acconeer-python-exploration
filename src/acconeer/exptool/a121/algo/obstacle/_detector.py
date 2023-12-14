# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool.a121._core.entities.configs.config_enums import PRF
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    PERCEIVED_WAVELENGTH,
    AlgoBase,
    AlgoConfigBase,
    PeakSortingMethod,
    calculate_loopback_peak_location,
)

from ._bilaterator import (
    Bilaterator,
    BilateratorResult,
)
from ._processors import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
    apply_max_depth_filter,
)


opser.register_json_presentable(a121.SessionConfig)


@attrs.mutable(kw_only=True)
class DetectorContext(AlgoBase):
    single_sensor_contexts: Dict[int, SingleSensorContext] = attrs.field(factory=dict)
    calibration_session_config: Optional[a121.SessionConfig] = attrs.field(default=None)

    @property
    def sensor_ids(self) -> list[int]:
        return list(self.single_sensor_contexts.keys())


@attrs.mutable(kw_only=True)
class SingleSubsweepContext(AlgoBase):
    mean_sweep: npt.NDArray[np.float_]
    std_sweep: npt.NDArray[np.float_]


@attrs.mutable(kw_only=True)
class SingleSensorContext(AlgoBase):
    subsweep_contexts: List[SingleSubsweepContext] = attrs.field(factory=list)
    reference_temperature: Optional[float] = attrs.field(default=None)
    loopback_peak_location_m: Optional[float] = attrs.field(default=None)


@attributes_doc
@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=0.15)
    """Start point of measurement interval in meters."""

    end_m: float = attrs.field(default=0.6)
    """End point of measurement interval in meters."""

    step_length: int = attrs.field(default=2)
    """Used to set step length. In unit approx. 2.5 mm."""

    hwaas: int = attrs.field(default=12)
    """Hardware averaging. Higher gives better SNR but increase power
    consumption and lower sweep rate."""

    profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_3, converter=a121.Profile)
    """Profile, 1-5. Higher equals better SNR and lower increase resolution.
    A recommendation is Profile 1 closer than 20 cm and Profile 3 beyond."""

    max_robot_speed: float = attrs.field(default=0.5)
    """Sets the sweep rate after the maximum robot speed in meters per second"""

    sweeps_per_frame: int = attrs.field(default=16)
    """Number of sweeps per frame. The length of the FFT to estimate speed or angle."""

    num_frames_in_recorded_threshold: int = attrs.field(default=50)
    """Number of frames used when calibrating threshold."""

    num_std_threshold: float = attrs.field(default=5)
    """Number of standard deviations added to the threshold."""

    num_mean_threshold: float = attrs.field(default=2)
    """Number of means added to the threshold."""

    update_rate: float = attrs.field(default=50.0)
    """Sets the detector update rate."""

    subsweep_configurations: Optional[List[a121.SubsweepConfig]] = attrs.field(default=None)
    """Optional list of subsweep configurations that over-writes the sensor configuration."""

    peak_sorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.CLOSEST,
        converter=PeakSortingMethod,
    )
    """Sorting method of targets."""

    enable_bilateration: bool = attrs.field(default=False)
    """Enable two-sensor bilateration."""

    bilateration_sensor_spacing_m: float = attrs.field(default=0.05)
    """The sensor spacing in meters."""

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

        if self.sweeps_per_frame < 2:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "sweeps_per_frame",
                    "Must be larger than one for angle estimation.",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class DetectorResult:
    current_velocity: float = attrs.field(default=None)
    processor_results: Dict[int, ProcessorResult] = attrs.field(default=None)
    bilateration_result: Optional[BilateratorResult] = attrs.field(default=None)


@attrs.mutable(kw_only=True)
class DetectorStatus:
    detector_state: DetailedStatus
    ready_to_start: bool = attrs.field(default=False)


class DetailedStatus(enum.Enum):
    OK = enum.auto()
    END_LESSER_THAN_START = enum.auto()
    SENSOR_IDS_NOT_UNIQUE = enum.auto()
    CONTEXT_MISSING = enum.auto()
    CALIBRATION_MISSING = enum.auto()
    CONFIG_MISMATCH = enum.auto()


class Detector:
    """Obstacle detector
    :param client: Client
    :param sensor_id: Sensor id
    :param detector_config: Detector configuration
    :param context: Detector context
    """

    session_config: a121.SessionConfig
    processor_specs: List[ProcessorConfig]
    context: DetectorContext

    def __init__(
        self,
        *,
        client: a121.Client,
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
            self.detector_status = DetectorStatus(
                detector_state=DetailedStatus.CALIBRATION_MISSING,
                ready_to_start=False,
            )
        else:
            self.context = context
            self.detector_status = DetectorStatus(
                detector_state=DetailedStatus.OK,
                ready_to_start=True,
            )

        if self.detector_config.enable_bilateration:
            if len(sensor_ids) != 2:
                raise ValueError("Bilateration requires two, and only two, sensors.")
            self.bilaterator = Bilaterator(detector_config.bilateration_sensor_spacing_m)

        # Unless updated, assume that robot moves at max speed
        self.v_current = self.detector_config.max_robot_speed

        self.update_config(self.detector_config)
        self.true_zero_dist_idx = 0

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
        self._calibrate_threshold()

        self.context.calibration_session_config = self.session_config

        self.detector_status.detector_state = DetailedStatus.OK
        self.detector_status.ready_to_start = True

    def start(
        self,
        recorder: Optional[a121.Recorder] = None,
        _algo_group: Optional[h5py.Group] = None,
    ) -> None:
        if self.started:
            raise RuntimeError("Already started")

        if not self.detector_status.ready_to_start:
            raise RuntimeError("Not ready to start")

        sensor_config = self._get_sensor_config(self.detector_config)

        self.processors: Dict[int, Processor] = {}
        group = []
        for s_id in self.sensor_ids:
            sens_context = self.context.single_sensor_contexts[s_id]

            mean_sweeps: list[npt.NDArray[np.float_]] = []
            std_sweeps: list[npt.NDArray[np.float_]] = []

            for subsweep_idx in range(sensor_config.num_subsweeps):
                ssc = sens_context.subsweep_contexts[subsweep_idx]
                mean_sweeps.append(ssc.mean_sweep)
                std_sweeps.append(ssc.std_sweep)

            assert sens_context.loopback_peak_location_m is not None
            proc_context = ProcessorContext(
                mean_sweeps=mean_sweeps,
                std_sweeps=std_sweeps,
                loopback_peak_location_m=sens_context.loopback_peak_location_m,
                reference_temperature=sens_context.reference_temperature,
            )

            pc = ProcessorConfig(
                num_std_treshold=self.detector_config.num_std_threshold,
                num_mean_treshold=self.detector_config.num_mean_threshold,
                peak_sorting_method=self.detector_config.peak_sorting_method,
            )

            self.processors[s_id] = Processor(
                sensor_config=sensor_config,
                processor_config=pc,
                context=proc_context,
            )

            group.append({s_id: sensor_config})

        self.session_config = a121.SessionConfig(group, extended=True)

        self.client.setup_session(self.session_config)

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                if _algo_group is None:
                    _algo_group = recorder.require_algo_group("obstacle_detector")

                _record_algo_data(
                    _algo_group,
                    self.sensor_ids,
                    self.detector_config,
                    self.context,
                )

            self.client.attach_recorder(recorder)

        self.client.start_session()

        self.detector_status.ready_to_start = False

        self.started = True

    def get_next(self) -> DetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        results = self.client.get_next()
        assert isinstance(results, list)

        processor_results: Dict[int, ProcessorResult] = {}

        for r in results:
            sens_id = list(r.keys())[0]  # get the only sensor-id in that dict.
            processor_results[sens_id] = self.processors[sens_id].process(r[sens_id])

        if self.detector_config.enable_bilateration:
            target_list_1 = processor_results[self.sensor_ids[0]].targets
            target_list_2 = processor_results[self.sensor_ids[1]].targets
            time_offset = (
                results[1][self.sensor_ids[1]].tick_time - results[0][self.sensor_ids[0]].tick_time
            )
            bilateration_result = self.bilaterator.process(
                target_list_1, target_list_2, time_offset
            )
        else:
            bilateration_result = None

        return DetectorResult(
            current_velocity=self.v_current,
            processor_results=processor_results,
            bilateration_result=bilateration_result,
        )

    def update_robot_speed(self, v_current: float) -> None:
        self.v_current = v_current

    @staticmethod
    def get_obstacle_angle(v_current: float, v_measured: float) -> float:
        """
        Convert the measured speed of an object to an angle.

        The convention is that a robot moving forward has a positive robot speed
        and an object moving towards from the sensor has a negative measured speed.
        Therefore, for an object straight in front of the sensor, v_measured is
        approximately -v_current and the obstacle angle is positive and close
        to zero.
        """
        return float(np.arccos(-v_measured / v_current))

    def stop(self) -> Any:
        """Stops the measurement session."""
        if not self.started:
            raise RuntimeError("Already stopped")

        self.client.stop_session()

        self.detector_status.ready_to_start = True

        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()

        self.started = False

        return recorder_result

    def update_config(self, config: DetectorConfig) -> None:
        """Updates the session config and processor specification based on the detector
        configuration."""
        (
            self.session_config,
            self.processor_specs,
        ) = self._detector_to_session_config_and_processor_specs(
            config=config, sensor_ids=self.sensor_ids
        )

        if not (self.context.calibration_session_config == self.session_config):
            self.detector_status.detector_state = DetailedStatus.CALIBRATION_MISSING
            self.detector_status.ready_to_start = False

    @classmethod
    def _get_sensor_config(cls, detector_config: DetectorConfig) -> a121.SensorConfig:
        if detector_config.subsweep_configurations is None:
            start_p = int(detector_config.start_m / APPROX_BASE_STEP_LENGTH_M)
            num_p = int(
                (detector_config.end_m - detector_config.start_m)
                / (APPROX_BASE_STEP_LENGTH_M * detector_config.step_length)
            )

            subsweeps = [
                a121.SubsweepConfig(
                    start_point=start_p,
                    num_points=num_p,
                    step_length=detector_config.step_length,
                    profile=detector_config.profile,
                    hwaas=detector_config.hwaas,
                    prf=PRF.PRF_15_6_MHz,
                )
            ]

        else:
            subsweeps = detector_config.subsweep_configurations

        for subsweep in subsweeps:
            subsweep.phase_enhancement = True

        return a121.SensorConfig(
            sweeps_per_frame=detector_config.sweeps_per_frame,
            sweep_rate=detector_config.max_robot_speed / (PERCEIVED_WAVELENGTH / 2),
            inter_sweep_idle_state=a121.IdleState.READY,
            inter_frame_idle_state=a121.IdleState.READY,
            subsweeps=subsweeps,
        )

    @classmethod
    def _detector_to_session_config_and_processor_specs(
        cls, config: DetectorConfig, sensor_ids: list[int]
    ) -> Tuple[a121.SessionConfig, list[ProcessorConfig]]:
        processor_spec = ProcessorConfig(
            num_std_treshold=config.num_std_threshold,
            num_mean_treshold=config.num_mean_threshold,
        )

        sensor_config = cls._get_sensor_config(config)
        return (
            a121.SessionConfig({s_id: sensor_config for s_id in sensor_ids}, extended=True),
            [processor_spec] * len(sensor_ids),
        )

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

        # Sensors running simultaneously, profile 1 and direct leakage give low risk of cross talk.
        session_config = a121.SessionConfig(
            {sensor_id: sensor_config for sensor_id in self.sensor_ids},
            extended=True,
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

    def _calibrate_threshold(self) -> None:
        self._validate_ready_for_calibration()

        sensor_config = self._get_sensor_config(self.detector_config)
        session_config = a121.SessionConfig(
            {sensor_id: sensor_config for sensor_id in self.sensor_ids}, extended=True
        )
        self.client.setup_session(session_config)

        result_list: list[dict[int, a121.Result]] = []
        self.client.start_session()
        for _ in range(self.detector_config.num_frames_in_recorded_threshold):
            extended_result = self.client.get_next()
            assert isinstance(extended_result, list)
            assert all(isinstance(r, dict) for r in extended_result)
            result_list.append({i: r for d in extended_result for i, r in d.items()})
        self.client.stop_session()

        # Processor used for applying the depth filter
        processor = Processor(sensor_config=sensor_config, processor_config=ProcessorConfig())

        for s_id in self.sensor_ids:
            results: list[a121.Result] = [r[s_id] for r in result_list]
            depth_filtered_data = [processor.apply_depth_filter(result) for result in results]
            threshold_temp = np.mean([r.temperature for r in results])

            self.context.single_sensor_contexts[s_id].subsweep_contexts = []
            for subsweep_idx in range(sensor_config.num_subsweeps):
                subsweep_filtered_data = np.array(
                    [dfd[subsweep_idx] for dfd in depth_filtered_data]
                )

                abs_mean = np.abs(
                    np.mean(subsweep_filtered_data, axis=(0, 1))
                )  # Over the frame- and sweep dimension
                std = np.std(subsweep_filtered_data, axis=(0, 1))

                subsweep_mean = apply_max_depth_filter(
                    abs_mean, sensor_config.subsweeps[subsweep_idx]
                )

                ssc = SingleSubsweepContext(mean_sweep=subsweep_mean, std_sweep=std)
                self.context.single_sensor_contexts[s_id].subsweep_contexts.append(ssc)

            self.context.single_sensor_contexts[s_id].reference_temperature = float(threshold_temp)

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

        if context.single_sensor_contexts is None:
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
            [
                ctx.loopback_peak_location_m is None
                for ctx in context.single_sensor_contexts.values()
            ]
        )
        config_mismatch = (
            context.calibration_session_config != session_config
            or context.sensor_ids != sensor_ids
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
) -> Tuple[int, DetectorConfig, DetectorContext]:
    sensor_id = algo_group["sensor_ids"][()]
    config = DetectorConfig.from_json(algo_group["detector_config"][()])

    context_group = algo_group["context"]
    context = opser.deserialize(context_group, DetectorContext)

    return sensor_id, config, context
