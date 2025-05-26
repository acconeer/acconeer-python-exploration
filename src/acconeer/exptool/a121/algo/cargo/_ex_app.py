# Copyright (c) Acconeer AB, 2025
# All rights reserved

from __future__ import annotations

import warnings
from enum import Enum
from typing import Any, List, Optional, Tuple, Union

import attrs
import h5py
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    AlgoConfigBase,
    AlgoParamEnum,
    Controller,
)
from acconeer.exptool.a121.algo._base import AlgoBase, AlgoBaseT
from acconeer.exptool.a121.algo._utils import estimate_frame_rate
from acconeer.exptool.a121.algo.distance._detector import Detector as DistanceDetector
from acconeer.exptool.a121.algo.distance._detector import DetectorConfig as DistanceConfig
from acconeer.exptool.a121.algo.distance._detector import DetectorContext as DistanceContext
from acconeer.exptool.a121.algo.distance._detector import DetectorResult as DistanceResult
from acconeer.exptool.a121.algo.distance._detector import ReflectorShape
from acconeer.exptool.a121.algo.distance._processors import (
    ProcessorResult as DistanceProcessorResult,
)
from acconeer.exptool.a121.algo.presence._detector import Detector as PresenceDetector
from acconeer.exptool.a121.algo.presence._detector import DetectorConfig as PresenceConfig
from acconeer.exptool.a121.algo.presence._detector import DetectorContext as PresenceContext
from acconeer.exptool.a121.algo.presence._detector import DetectorResult as PresenceResult
from acconeer.exptool.a121.algo.presence._processors import Processor as PresenceProcessor


PRESENCE_RUN_TIME_S = 5.0
MIN_PRESENCE_UPDATE_RATE = 1.0


def container_size_converter(container_size: ContainerSize) -> ContainerSize:
    return ContainerSize(container_size)


@attributes_doc
@attrs.mutable(kw_only=True)
class CargoPresenceConfig(AlgoConfigBase):
    burst_rate: float = attrs.field(default=0.1)
    """Sets the presence burst range in Hz.
    Each burst is 5 s long, hence 0.2 Hz is the highest possible burst rate."""

    update_rate: float = attrs.field(default=6.0)
    """Update rate in Hz."""

    signal_quality: float = attrs.field(default=20)
    """Signal quality metric (higher = better signal, lower = less power consumption)."""

    sweeps_per_frame: int = attrs.field(default=12)
    """Number of sweeps per frame."""

    inter_detection_threshold: float = attrs.field(default=4)
    """Detection threshold for the inter-frame presence detection."""

    intra_detection_threshold: float = attrs.field(default=2.75)
    """Detection threshold for the intra-frame presence detection."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if self.burst_rate > (1 / PRESENCE_RUN_TIME_S):
            validation_results.append(
                a121.ValidationError(
                    self,
                    "burst_rate",
                    f"Must not be > {1 / PRESENCE_RUN_TIME_S} Hz.",
                )
            )

        if self.update_rate < 1:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "update_rate",
                    f"Must be at least {MIN_PRESENCE_UPDATE_RATE} Hz.",
                )
            )

        if self.sweeps_per_frame <= PresenceProcessor.NOISE_ESTIMATION_DIFF_ORDER:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "sweeps_per_frame",
                    f"Must be greater than {PresenceProcessor.NOISE_ESTIMATION_DIFF_ORDER}",
                )
            )

        return validation_results


@attributes_doc
@attrs.mutable(kw_only=True)
class UtilizationLevelConfig(AlgoConfigBase):
    update_rate: float = attrs.field(default=5)
    """Sets the detector update rate."""

    signal_quality: float = attrs.field(default=10)
    """Signal quality (dB).

    High quality equals higher HWAAS and better SNR but increases power consumption."""

    threshold_sensitivity: float = attrs.field(default=0)
    """Sensitivity of threshold.

    High sensitivity equals low detection threshold, low sensitivity equals high detection
    threshold."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return []


class ContainerSize(AlgoParamEnum):
    #               length_m  Presence    Distance
    CONTAINER_10_FT = (3.0, (0.8, 2.7), (0.3, 3.5))
    CONTAINER_20_FT = (6.0, (0.8, 5.7), (0.3, 6.5))
    CONTAINER_40_FT = (12.0, (0.8, 7.0), (0.3, 12.5))

    @property
    def length_m(self) -> float:
        return self.value[0]

    @property
    def presence_range(self) -> tuple[float, float]:
        return self.value[1]

    @property
    def distance_range(self) -> tuple[float, float]:
        return self.value[2]


@attributes_doc
@attrs.mutable(kw_only=True)
class ExAppConfig(AlgoConfigBase):
    activate_presence: bool = attrs.field()
    """Activates presence detection."""

    cargo_presence_config: Optional[CargoPresenceConfig] = attrs.field(factory=CargoPresenceConfig)
    """Configuration of presence detector."""

    activate_utilization_level: bool = attrs.field()
    """Activates utilization level detection."""

    utilization_level_config: Optional[UtilizationLevelConfig] = attrs.field(
        factory=UtilizationLevelConfig
    )
    """Configuration for utilization level measurements."""

    container_size: ContainerSize = attrs.field(
        default=ContainerSize.CONTAINER_20_FT, converter=container_size_converter
    )
    """Container size. Sets the detection range for utilization level detection and for presence detection."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []
        if self.cargo_presence_config is not None:
            validation_results.extend(self.cargo_presence_config._collect_validation_results())

        if self.utilization_level_config is not None:
            validation_results.extend(self.utilization_level_config._collect_validation_results())

        if not self.activate_presence and not self.activate_utilization_level:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "activate_presence",
                    "One detector needs to be activated.",
                )
            )

        return validation_results

    @classmethod
    def from_dict(cls: type[AlgoBaseT], d: dict[str, Any]) -> AlgoBaseT:
        d["cargo_presence_config"] = CargoPresenceConfig.from_dict(d["cargo_presence_config"])
        d["utilization_level_config"] = UtilizationLevelConfig.from_dict(
            d["utilization_level_config"]
        )

        return cls(**d)


@attrs.mutable(kw_only=True)
class ExAppContext(AlgoBase):
    presence_context: Optional[PresenceContext] = attrs.field(default=None)
    distance_context: Optional[DistanceContext] = attrs.field(default=None)

    @classmethod
    def from_dict(cls: type[AlgoBaseT], d: dict[str, Any]) -> AlgoBaseT:
        if d["presence_context"] is not None:
            d["presence_context"] = PresenceContext.from_dict(d["presence_context"])
        if d["distance_context"] is not None:
            d["distance_context"] = DistanceContext.from_dict(d["distance_context"])

        return cls(**d)


@attrs.frozen(kw_only=True)
class ExAppResult:
    mode: _Mode = attrs.field()
    """Measurement mode, Presence or Distance."""

    presence_detected: Optional[bool] = attrs.field()
    """`True` if presence was detected, `False` otherwise."""

    inter_presence_score: Optional[float] = attrs.field()
    """A measure of the amount of slow motion detected."""

    intra_presence_score: Optional[float] = attrs.field()
    """A measure of the amount of fast motion detected."""

    distance: Optional[float] = attrs.field()
    """The measured distance by the distance detector."""

    level_m: Optional[float] = attrs.field()
    """The utilization level in m."""

    level_percent: Optional[float] = attrs.field()
    """The utilization level in percentage."""

    distance_processor_result: Optional[List[DistanceProcessorResult]] = attrs.field()
    """Distance processor result, used for plotting."""

    service_result: a121.Result = attrs.field()


class _Mode(Enum):
    PRESENCE = 0
    DISTANCE = 1


class ExApp(Controller[ExAppConfig, ExAppResult]):
    detector: Union[DistanceDetector, PresenceDetector]

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        ex_app_config: ExAppConfig,
        ex_app_context: Optional[ExAppContext] = None,
    ) -> None:
        super().__init__(client=client, config=ex_app_config)
        self.sensor_id = sensor_id
        if ex_app_context is None:
            self.ex_app_context = ExAppContext()
        else:
            self.ex_app_context = ex_app_context

        self.ex_app_config = ex_app_config
        self.presence_context = self.ex_app_context.presence_context
        self.distance_context = self.ex_app_context.distance_context

        self.container_size = ex_app_config.container_size
        self.activate_presence = ex_app_config.activate_presence
        self.cargo_presence_config = ex_app_config.cargo_presence_config
        self.activate_utilization_level = ex_app_config.activate_utilization_level
        self.utilization_level_config = ex_app_config.utilization_level_config

        if self.activate_presence and self.activate_utilization_level:
            self.dual_detectors = True
        elif not self.activate_presence and not self.activate_utilization_level:
            msg = "No detector activated"
            raise AssertionError(msg)
        else:
            self.dual_detectors = False

        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        if self.activate_presence:
            self.initialize_presence()

        if self.activate_utilization_level:
            self.initialize_distance()

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("cargo")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.ex_app_config,
                    self.ex_app_context,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        if self.dual_detectors:
            self.start_dual_detectors(recorder, algo_group)
        elif self.activate_presence:
            self.detector = PresenceDetector(
                client=self.client,
                sensor_id=self.sensor_id,
                detector_config=self.presence_config,
                detector_context=self.presence_context,
            )
            self.detector.start(recorder=recorder, _algo_group=algo_group)
        else:
            self.detector = DistanceDetector(
                client=self.client,
                sensor_ids=[self.sensor_id],
                detector_config=self.distance_config,
                context=self.distance_context,
            )
            self.detector.start(recorder=recorder, _algo_group=algo_group)

        self.started = True

    def initialize_presence(self) -> None:
        assert self.cargo_presence_config is not None
        self.num_presence_frames_in_burst = int(
            round((PRESENCE_RUN_TIME_S * self.cargo_presence_config.update_rate))
        )
        self.num_presence_frames_in_cycle = (
            self.cargo_presence_config.update_rate / self.cargo_presence_config.burst_rate
        )
        self.presence_count = 0
        start_m, end_m = self.container_size.presence_range
        self.presence_config = self.get_presence_config(self.cargo_presence_config, start_m, end_m)

        sensor_config = PresenceDetector._get_sensor_config(self.presence_config)
        session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        if self.ex_app_context is None:
            self.presence_context = PresenceContext(
                estimated_frame_rate=estimate_frame_rate(self.client, session_config)
            )
            self.ex_app_context = ExAppContext(presence_context=self.presence_context)
        elif self.ex_app_context.presence_context is None:
            self.presence_context = PresenceContext(
                estimated_frame_rate=estimate_frame_rate(self.client, session_config)
            )
            self.ex_app_context.presence_context = self.presence_context
        else:
            self.presence_context = self.ex_app_context.presence_context

    def initialize_distance(self) -> None:
        assert self.utilization_level_config is not None
        start_m, end_m = self.container_size.distance_range
        self.distance_config = self.get_distance_config(
            self.utilization_level_config, start_m, end_m
        )

        if self.ex_app_context is None or self.ex_app_context.distance_context is None:
            self.detector = DistanceDetector(
                client=self.client,
                sensor_ids=[self.sensor_id],
                detector_config=self.distance_config,
                context=self.distance_context,
            )

            self.detector.calibrate_detector()
            if self.ex_app_context is None:
                self.ex_app_context = ExAppContext(distance_context=self.detector.context)
            else:
                self.ex_app_context.distance_context = self.detector.context

        self.distance_context = self.ex_app_context.distance_context

    def start_dual_detectors(
        self, recorder: Optional[a121.Recorder], algo_group: Optional[h5py.Group]
    ) -> None:
        assert self.cargo_presence_config is not None
        assert self.utilization_level_config is not None

        if self.utilization_level_config.update_rate > self.cargo_presence_config.burst_rate:
            self.burst_nbr_switch = (
                self.utilization_level_config.update_rate / self.cargo_presence_config.burst_rate
                - self.utilization_level_config.update_rate * PRESENCE_RUN_TIME_S
            )
            self.burst_nbr_switch = int(round(self.burst_nbr_switch))
            self.steering_mode = _Mode.DISTANCE

        else:
            self.burst_nbr_switch = (
                self.cargo_presence_config.burst_rate / self.utilization_level_config.update_rate
                - self.cargo_presence_config.burst_rate * PRESENCE_RUN_TIME_S
            )
            self.steering_mode = _Mode.PRESENCE

        self.detector = DistanceDetector(
            client=self.client,
            sensor_ids=[self.sensor_id],
            detector_config=self.distance_config,
            context=self.distance_context,
        )
        self.detector.start(recorder=recorder, _algo_group=algo_group)
        self.burst_count = 0
        self.presence_count = self.num_presence_frames_in_burst

    @classmethod
    def get_presence_config(
        cls, cargo_presence_config: CargoPresenceConfig, start_m: float, end_m: float
    ) -> PresenceConfig:
        return PresenceConfig(
            frame_rate=cargo_presence_config.update_rate,
            start_m=start_m,
            end_m=end_m,
            sweeps_per_frame=cargo_presence_config.sweeps_per_frame,
            automatic_subsweeps=True,
            signal_quality=cargo_presence_config.signal_quality,
            intra_detection_threshold=cargo_presence_config.intra_detection_threshold,
            intra_frame_time_const=0.15,
            intra_output_time_const=0.3,
            inter_detection_threshold=cargo_presence_config.inter_detection_threshold,
            inter_frame_slow_cutoff=0.2,
            inter_frame_fast_cutoff=cargo_presence_config.update_rate,
            inter_frame_deviation_time_const=0.5,
            inter_output_time_const=2,
            inter_frame_presence_timeout=None,
        )

    @classmethod
    def get_distance_config(
        cls, utilization_level_config: UtilizationLevelConfig, start_m: float, end_m: float
    ) -> DistanceConfig:
        return DistanceConfig(
            update_rate=utilization_level_config.update_rate,
            start_m=start_m,
            end_m=end_m,
            signal_quality=utilization_level_config.signal_quality,
            threshold_sensitivity=utilization_level_config.threshold_sensitivity,
            reflector_shape=ReflectorShape.PLANAR,
        )

    def get_next(self) -> ExAppResult:
        distance_result: Optional[dict[int, DistanceResult]] = None
        presence_result: Optional[PresenceResult] = None

        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        if isinstance(self.detector, PresenceDetector):
            presence_result = self.detector.get_next()
            current_mode = _Mode.PRESENCE
            self.presence_count += 1
        else:
            distance_result = self.detector.get_next()
            current_mode = _Mode.DISTANCE

        if self.dual_detectors:
            if self.presence_count < self.num_presence_frames_in_burst:
                skip_result = False
            else:
                skip_result = self.determine_swapping(current_mode)
        elif self.activate_presence:
            skip_result = False
            if (
                self.presence_count > self.num_presence_frames_in_burst
                and self.presence_count < self.num_presence_frames_in_cycle
            ):
                skip_result = True
            elif self.presence_count == self.num_presence_frames_in_cycle:
                if self.presence_count == self.num_presence_frames_in_burst:
                    skip_result = False
                else:
                    skip_result = True

                self.presence_count = 0
                self.detector.stop_detector()
                self.detector.start(recorder=None, _algo_group=None)

        if current_mode == _Mode.DISTANCE:
            assert distance_result is not None
            service_result = distance_result[self.sensor_id].service_extended_result[0][
                self.sensor_id
            ]
            presence_detected = None
            inter_presence_score = None
            intra_presence_score = None
            distances = distance_result[self.sensor_id].distances
            distance_processor_result = distance_result[self.sensor_id].processor_results
            if distances is not None and len(distances) != 0:
                distance = distances[0]
                level_m = self.ex_app_config.container_size.length_m - distance
                level_percent = level_m / self.ex_app_config.container_size.length_m * 100
            else:
                distance = None
                level_m = None
                level_percent = None
        else:
            assert presence_result is not None
            service_result = presence_result.service_result
            if skip_result:
                presence_detected = None
                inter_presence_score = None
                intra_presence_score = None
                distance = None
                level_m = None
                level_percent = None
                distance_processor_result = None
            else:
                presence_detected = presence_result.presence_detected
                inter_presence_score = presence_result.inter_presence_score
                intra_presence_score = presence_result.intra_presence_score
                distance = None
                level_m = None
                level_percent = None
                distance_processor_result = None

        return ExAppResult(
            mode=current_mode,
            presence_detected=presence_detected,
            inter_presence_score=inter_presence_score,
            intra_presence_score=intra_presence_score,
            distance=distance,
            level_m=level_m,
            level_percent=level_percent,
            distance_processor_result=distance_processor_result,
            service_result=service_result,
        )

    def determine_swapping(self, current_mode: _Mode) -> bool:
        skip_result = False
        if self.steering_mode == _Mode.DISTANCE:
            if current_mode == _Mode.PRESENCE:
                self.swap_config(current_mode)
            else:
                self.burst_count += 1
                if self.burst_count > self.burst_nbr_switch:
                    self.swap_config(current_mode)
                    self.presence_count = 0
        else:
            if current_mode == _Mode.DISTANCE:
                self.swap_config(current_mode)
                self.presence_count = 0
            else:
                if self.presence_count == self.num_presence_frames_in_cycle:
                    self.burst_count += 1
                    if self.burst_count > self.burst_nbr_switch:
                        self.swap_config(current_mode)
                    else:
                        self.presence_count = 0
                        self.detector.stop_detector()
                        self.detector.start(recorder=None, _algo_group=None)

                if self.presence_count > self.num_presence_frames_in_burst:
                    skip_result = True

        return skip_result

    def swap_config(self, current_mode: _Mode) -> None:
        self.detector.stop_detector()

        if current_mode == _Mode.DISTANCE:
            self.detector = PresenceDetector(
                client=self.client,
                sensor_id=self.sensor_id,
                detector_config=self.presence_config,
                detector_context=self.presence_context,
            )
        else:
            self.detector = DistanceDetector(
                client=self.client,
                sensor_ids=[self.sensor_id],
                detector_config=self.distance_config,
                context=self.distance_context,
            )

        self.detector.start(recorder=None, _algo_group=None)
        self.burst_count = 0

    def update_config(self, config: ExAppConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        recorder_result = self.detector.stop()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    ex_app_config: ExAppConfig,
    ex_app_context: ExAppContext,
) -> None:
    if "ex_app_sensor_id" in algo_group:
        algo_group.attrs["ex_app_sensor_id"] = sensor_id
        del algo_group["ex_app_config"]
        _create_h5_string_dataset(algo_group, "ex_app_config", ex_app_config.to_json())
        del algo_group["ex_app_context"]
        ex_app_context_group = algo_group.create_group("ex_app_context")
    else:
        algo_group.create_dataset(
            "ex_app_sensor_id",
            data=sensor_id,
            track_times=False,
        )

        _create_h5_string_dataset(algo_group, "ex_app_config", ex_app_config.to_json())
        ex_app_context_group = algo_group.create_group("ex_app_context")

    opser.serialize(ex_app_context, ex_app_context_group)


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, ExAppConfig, ExAppContext]:
    sensor_id = int(algo_group["ex_app_sensor_id"][()])
    config = ExAppConfig.from_json(algo_group["ex_app_config"][()])
    ex_app_context = opser.deserialize(algo_group["ex_app_context"], ExAppContext)
    return sensor_id, config, ex_app_context
