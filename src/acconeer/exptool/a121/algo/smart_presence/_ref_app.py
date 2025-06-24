# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import copy
import warnings
from enum import Enum
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_isclose
from acconeer.exptool.a121._core.entities.configs.config_enums import IdleState, Profile
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._base import AlgoBase, AlgoBaseT
from acconeer.exptool.a121.algo._utils import estimate_frame_rate
from acconeer.exptool.a121.algo.presence._detector import (
    AlgoConfigBase,
    Controller,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
)

from ._processor import Processor, ProcessorConfig, ProcessorResult


SPARSE_IQ_PPC = 24


def optional_profile_converter(profile: Optional[Profile]) -> Optional[Profile]:
    if profile is None:
        return None

    return Profile(profile)


def idle_state_converter(idle_state: IdleState) -> IdleState:
    return IdleState(idle_state)


@attributes_doc
@attrs.mutable(kw_only=True)
class PresenceZoneConfig(DetectorConfig):
    num_zones: int = attrs.field(default=7)
    """Maximum number of detection zones."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return super()._collect_validation_results()


@attributes_doc
@attrs.mutable(kw_only=True)
class PresenceWakeUpConfig(PresenceZoneConfig):
    num_zones_for_wake_up: int = attrs.field(default=1)
    """Number of detected zones needed for wake up."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results = super()._collect_validation_results()

        if self.num_zones_for_wake_up > self.num_zones:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "num_zones_for_wake_up",
                    f"Must not be more than number of zones ({self.num_zones})",
                )
            )

        return validation_results


@attributes_doc
@attrs.mutable(kw_only=True)
class RefAppConfig(AlgoConfigBase):
    nominal_config: PresenceZoneConfig = attrs.field(factory=PresenceZoneConfig)
    """Configuration used to keep detection."""

    wake_up_config: Optional[PresenceWakeUpConfig] = attrs.field(factory=PresenceWakeUpConfig)
    """Configuration used for wake up."""

    wake_up_mode: bool = attrs.field(default=True)
    """Switch between two configurations based on presence detection."""

    show_all_detected_zones: bool = attrs.field(default=False)
    """Visualize all detected zones in the circle sector."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        validation_results.extend(self.nominal_config._collect_validation_results())

        if self.wake_up_config is not None:
            validation_results.extend(self.wake_up_config._collect_validation_results())

        return validation_results

    @classmethod
    def from_dict(cls: type[AlgoBaseT], d: dict[str, Any]) -> AlgoBaseT:
        try:
            d["nominal_config"] = presence_zone_config_timeline.migrate(d["nominal_config"])
            d["wake_up_config"] = presence_wake_up_config_timeline.migrate(d["wake_up_config"])
        except tm.core.MigrationErrorGroup as exc:
            raise TypeError() from exc

        return cls(**d)


@attrs.mutable(kw_only=True)
class RefAppContext(AlgoBase):
    nominal_detector_context: Optional[DetectorContext] = attrs.field(default=None)
    wake_up_detector_context: Optional[DetectorContext] = attrs.field(default=None)

    @classmethod
    def from_dict(cls: type[AlgoBaseT], d: dict[str, Any]) -> AlgoBaseT:
        if d["nominal_detector_context"] is not None:
            d["nominal_detector_context"] = DetectorContext.from_dict(
                d["nominal_detector_context"]
            )
        if d["wake_up_detector_context"] is not None:
            d["wake_up_detector_context"] = DetectorContext.from_dict(
                d["wake_up_detector_context"]
            )

        return cls(**d)


@attrs.frozen(kw_only=True)
class RefAppResult:
    zone_limits: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    "The upper limit for each zone."

    presence_detected: bool = attrs.field()
    """True if presence was detected, False otherwise."""

    max_presence_zone: Optional[int] = attrs.field()
    """The zone for maximum presence score if presence detected, else None."""

    total_zone_detections: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_isclose)
    """Detection result for all zones."""

    inter_presence_score: float = attrs.field()
    """A measure of the amount of slow motion detected."""

    inter_zone_detections: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_isclose)
    """Slow motion presence detection result for all zones."""

    max_inter_zone: Optional[int] = attrs.field()
    """The zone for maximum slow motion presence score if slow presence detected, else None."""

    intra_presence_score: float = attrs.field()
    """A measure of the amount of fast motion detected."""

    intra_zone_detections: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_isclose)
    """Fast motion presence detection result for all zones."""

    max_intra_zone: Optional[int] = attrs.field()
    """The zone for maximum fast motion presence score if fast presence detected, else None."""

    used_config: _Mode = attrs.field()
    """The configuration used for the measurement."""

    wake_up_detections: Optional[npt.NDArray[np.int_]] = attrs.field()
    """Wake up detection result."""

    switch_delay: bool = attrs.field()
    """True if data was collected during switch delay."""

    service_result: a121.Result = attrs.field()


class _Mode(Enum):
    WAKE_UP_CONFIG = 0
    NOMINAL_CONFIG = 1


class RefApp(Controller[RefAppConfig, RefAppResult]):
    wake_up_detections: Optional[npt.NDArray[np.int_]]
    ref_app_context: RefAppContext

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        ref_app_config: RefAppConfig,
        ref_app_context: Optional[RefAppContext] = None,
    ) -> None:
        super().__init__(client=client, config=ref_app_config)
        self.sensor_id = sensor_id
        if ref_app_context is None:
            self.ref_app_context = RefAppContext()
        else:
            self.ref_app_context = ref_app_context

        self.started = False
        self.delay_count = 0
        if ref_app_config.wake_up_mode:
            assert ref_app_config.wake_up_config is not None
            self.wake_up_detections = np.zeros(ref_app_config.wake_up_config.num_zones, dtype=int)
            self.max_zone_time_n = int(np.around(2 * ref_app_config.wake_up_config.frame_rate))
        else:
            self.wake_up_detections = None

    def start(
        self, recorder: Optional[a121.Recorder] = None, algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        self.nominal_detector_config = self.config.nominal_config

        sensor_config = Detector._get_sensor_config(self.nominal_detector_config)
        session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )
        detector_config: DetectorConfig

        if self.ref_app_context.nominal_detector_context is None:
            self.nominal_detector_context = DetectorContext(
                estimated_frame_rate=estimate_frame_rate(self.client, session_config)
            )
            self.ref_app_context = RefAppContext(
                nominal_detector_context=self.nominal_detector_context
            )
        else:
            self.nominal_detector_context = self.ref_app_context.nominal_detector_context

        distances = np.linspace(
            self.config.nominal_config.start_m,
            self.config.nominal_config.end_m,
            sum([subsweep.num_points for subsweep in sensor_config.subsweeps]),
        )
        self.config.nominal_config.num_zones = min(
            self.config.nominal_config.num_zones, distances.size
        )

        self.nominal_processor_config = ProcessorConfig(
            num_zones=self.config.nominal_config.num_zones
        )

        if self.config.wake_up_mode:
            self._mode = _Mode.WAKE_UP_CONFIG
            assert self.config.wake_up_config is not None

            self.wake_up_detector_config = self.config.wake_up_config

            sensor_config = Detector._get_sensor_config(self.wake_up_detector_config)
            session_config = a121.SessionConfig(
                {self.sensor_id: sensor_config},
                extended=False,
            )

            if self.ref_app_context.wake_up_detector_context is None:
                self.wake_up_detector_context = DetectorContext(
                    estimated_frame_rate=estimate_frame_rate(self.client, session_config)
                )
                self.ref_app_context.wake_up_detector_context = self.wake_up_detector_context
            else:
                self.wake_up_detector_context = self.ref_app_context.wake_up_detector_context

            distances = np.linspace(
                self.config.wake_up_config.start_m,
                self.config.wake_up_config.end_m,
                sum([subsweep.num_points for subsweep in sensor_config.subsweeps]),
            )
            self.config.wake_up_config.num_zones = min(
                self.config.wake_up_config.num_zones, distances.size
            )
            self.config.wake_up_config.num_zones_for_wake_up = min(
                self.config.wake_up_config.num_zones_for_wake_up,
                self.config.wake_up_config.num_zones,
            )

            self.wake_up_processor_config = ProcessorConfig(
                num_zones=self.config.wake_up_config.num_zones
            )

            detector_config = self.wake_up_detector_config
            detector_context = self.wake_up_detector_context
            processor_config = self.wake_up_processor_config
        else:
            self._mode = _Mode.NOMINAL_CONFIG
            detector_config = self.nominal_detector_config
            detector_context = self.nominal_detector_context
            processor_config = self.nominal_processor_config

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("smart_presence")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.config,
                    self.ref_app_context,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        self.detector = Detector(
            client=self.client,
            sensor_id=self.sensor_id,
            detector_config=detector_config,
            detector_context=detector_context,
        )
        self.detector.start(recorder=recorder, _algo_group=algo_group)
        assert self.detector.detector_metadata is not None
        session_config = self.detector.session_config

        self.ref_app_processor = Processor(
            processor_config,
            detector_config,
            session_config,
            self.detector.detector_metadata,
        )

        self.max_switch_delay_n = (
            np.maximum(
                (
                    self.config.nominal_config.inter_frame_deviation_time_const
                    + self.config.nominal_config.inter_output_time_const
                ),
                (
                    self.config.nominal_config.intra_frame_time_const
                    + self.config.nominal_config.intra_output_time_const
                ),
            )
            * self.config.nominal_config.frame_rate
        )

        self.started = True

    def get_next(self) -> RefAppResult:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        result = self.detector.get_next()
        processor_result = self.ref_app_processor.process(result)

        used_config = self._mode
        if self.config.wake_up_mode:
            self.determine_swapping(result, processor_result)

        return RefAppResult(
            zone_limits=processor_result.zone_limits,
            presence_detected=result.presence_detected,
            max_presence_zone=processor_result.max_presence_zone,
            total_zone_detections=processor_result.total_zone_detections,
            inter_presence_score=result.inter_presence_score,
            inter_zone_detections=processor_result.inter_zone_detections,
            max_inter_zone=processor_result.max_inter_zone,
            intra_presence_score=result.intra_presence_score,
            intra_zone_detections=processor_result.intra_zone_detections,
            max_intra_zone=processor_result.max_intra_zone,
            used_config=used_config,
            wake_up_detections=copy.deepcopy(self.wake_up_detections),
            switch_delay=self.delay_count > 0,
            service_result=result.service_result,
        )

    def determine_swapping(
        self, result: DetectorResult, processor_result: ProcessorResult
    ) -> None:
        if self.delay_count == 0:
            if self._mode == _Mode.WAKE_UP_CONFIG and result.presence_detected:
                assert self.config.wake_up_config is not None
                assert self.wake_up_detections is not None
                num_detections = 0
                for i, zone_detection in enumerate(processor_result.total_zone_detections):
                    if zone_detection == 1:
                        self.wake_up_detections[i] = self.max_zone_time_n

                    if self.wake_up_detections[i] > 0:
                        num_detections += 1
                        self.wake_up_detections[i] -= 1

                if num_detections >= self.config.wake_up_config.num_zones_for_wake_up:
                    self.swap_config(
                        self.nominal_detector_config,
                        self.nominal_processor_config,
                        self.nominal_detector_context,
                    )
                    self._mode = _Mode.NOMINAL_CONFIG
                    self.delay_count += 1
            elif self._mode == _Mode.NOMINAL_CONFIG and not result.presence_detected:
                self.swap_config(
                    self.wake_up_detector_config,
                    self.wake_up_processor_config,
                    self.wake_up_detector_context,
                )
                self._mode = _Mode.WAKE_UP_CONFIG
        else:
            if self.delay_count == 1:
                assert self.wake_up_detections is not None
                self.wake_up_detections.fill(0)

            self.delay_count += 1
            if self.delay_count >= self.max_switch_delay_n + 1 or result.presence_detected:
                self.delay_count = 0

    def swap_config(
        self,
        detector_config: DetectorConfig,
        processor_config: ProcessorConfig,
        detector_context: DetectorContext,
    ) -> None:
        self.detector.stop_detector()

        self.detector = Detector(
            client=self.client,
            sensor_id=self.sensor_id,
            detector_config=detector_config,
            detector_context=detector_context,
        )

        self.detector.start(recorder=None, _algo_group=None)
        assert self.detector.detector_metadata is not None

        session_config = self.detector.session_config
        processor_config = ProcessorConfig(num_zones=processor_config.num_zones)

        self.ref_app_processor = Processor(
            processor_config, detector_config, session_config, self.detector.detector_metadata
        )

    def update_config(self, config: RefAppConfig) -> None:
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
    ref_app_config: RefAppConfig,
    ref_app_context: RefAppContext,
) -> None:
    algo_group.create_dataset(
        "ref_app_sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "ref_app_config", ref_app_config.to_json())
    _create_h5_string_dataset(algo_group, "ref_app_context", ref_app_context.to_json())


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, RefAppConfig, RefAppContext]:
    sensor_id = int(algo_group["ref_app_sensor_id"][()])
    config = RefAppConfig.from_json(algo_group["ref_app_config"][()])
    ref_app_context = RefAppContext.from_json(algo_group["ref_app_context"][()])
    return sensor_id, config, ref_app_context


@attrs.mutable(kw_only=True)
class _PresenceZoneConfig_v0(AlgoConfigBase):
    num_zones: int = attrs.field(default=7)
    start_m: float = attrs.field(default=0.3)
    end_m: float = attrs.field(default=2.5)
    profile: Optional[a121.Profile] = attrs.field(
        default=None, converter=optional_profile_converter
    )
    step_length: Optional[int] = attrs.field(default=None)
    frame_rate: float = attrs.field(default=12.0)
    sweeps_per_frame: int = attrs.field(default=16)
    automatic_subsweeps: bool = attrs.field(default=False)
    signal_quality: float = attrs.field(default=15.0)
    hwaas: int = attrs.field(default=32)
    inter_frame_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.DEEP_SLEEP, converter=idle_state_converter
    )
    intra_enable: bool = attrs.field(default=True)
    intra_detection_threshold: float = attrs.field(default=1.3)
    intra_frame_time_const: float = attrs.field(default=0.15)
    intra_output_time_const: float = attrs.field(default=0.3)
    inter_enable: bool = attrs.field(default=True)
    inter_detection_threshold: float = attrs.field(default=1)
    inter_frame_fast_cutoff: float = attrs.field(default=6.0)
    inter_frame_slow_cutoff: float = attrs.field(default=0.2)
    inter_frame_deviation_time_const: float = attrs.field(default=0.5)
    inter_output_time_const: float = attrs.field(default=2)
    inter_frame_presence_timeout: Optional[int] = attrs.field(default=3)
    inter_phase_boost: bool = attrs.field(default=False)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return []

    def migrate(self) -> PresenceZoneConfig:
        return PresenceZoneConfig(
            num_zones=self.num_zones,
            start_m=self.start_m,
            end_m=self.end_m,
            profile=self.profile,
            step_length=self.step_length,
            frame_rate=self.frame_rate,
            sweeps_per_frame=self.sweeps_per_frame,
            automatic_subsweeps=self.automatic_subsweeps,
            signal_quality=self.signal_quality,
            hwaas=self.hwaas,
            inter_frame_idle_state=self.inter_frame_idle_state,
            intra_enable=self.intra_enable,
            intra_detection_threshold=self.intra_detection_threshold,
            intra_frame_time_const=self.intra_frame_time_const,
            intra_output_time_const=self.intra_output_time_const,
            inter_enable=self.inter_enable,
            inter_detection_threshold=self.inter_detection_threshold,
            inter_frame_fast_cutoff=self.inter_frame_fast_cutoff,
            inter_frame_slow_cutoff=self.inter_frame_slow_cutoff,
            inter_frame_deviation_time_const=self.inter_frame_deviation_time_const,
            inter_output_time_const=self.inter_output_time_const,
            inter_frame_presence_timeout=self.inter_frame_presence_timeout,
            # inter_phase_boost is removed
        )


@attrs.mutable(kw_only=True)
class _PresenceWakeUpConfig_v0(AlgoConfigBase):
    num_zones_for_wake_up: int = attrs.field(default=1)
    num_zones: int = attrs.field(default=7)
    start_m: float = attrs.field(default=0.3)
    end_m: float = attrs.field(default=2.5)
    profile: Optional[a121.Profile] = attrs.field(
        default=None, converter=optional_profile_converter
    )
    step_length: Optional[int] = attrs.field(default=None)
    frame_rate: float = attrs.field(default=12.0)
    sweeps_per_frame: int = attrs.field(default=16)
    automatic_subsweeps: bool = attrs.field(default=False)
    signal_quality: float = attrs.field(default=15.0)
    hwaas: int = attrs.field(default=32)
    inter_frame_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.DEEP_SLEEP, converter=idle_state_converter
    )
    intra_enable: bool = attrs.field(default=True)
    intra_detection_threshold: float = attrs.field(default=1.3)
    intra_frame_time_const: float = attrs.field(default=0.15)
    intra_output_time_const: float = attrs.field(default=0.3)
    inter_enable: bool = attrs.field(default=True)
    inter_detection_threshold: float = attrs.field(default=1)
    inter_frame_fast_cutoff: float = attrs.field(default=6.0)
    inter_frame_slow_cutoff: float = attrs.field(default=0.2)
    inter_frame_deviation_time_const: float = attrs.field(default=0.5)
    inter_output_time_const: float = attrs.field(default=2)
    inter_frame_presence_timeout: Optional[int] = attrs.field(default=3)
    inter_phase_boost: bool = attrs.field(default=False)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return []

    def migrate(self) -> PresenceWakeUpConfig:
        return PresenceWakeUpConfig(
            num_zones_for_wake_up=self.num_zones_for_wake_up,
            num_zones=self.num_zones,
            start_m=self.start_m,
            end_m=self.end_m,
            profile=self.profile,
            step_length=self.step_length,
            frame_rate=self.frame_rate,
            sweeps_per_frame=self.sweeps_per_frame,
            automatic_subsweeps=self.automatic_subsweeps,
            signal_quality=self.signal_quality,
            hwaas=self.hwaas,
            inter_frame_idle_state=self.inter_frame_idle_state,
            intra_enable=self.intra_enable,
            intra_detection_threshold=self.intra_detection_threshold,
            intra_frame_time_const=self.intra_frame_time_const,
            intra_output_time_const=self.intra_output_time_const,
            inter_enable=self.inter_enable,
            inter_detection_threshold=self.inter_detection_threshold,
            inter_frame_fast_cutoff=self.inter_frame_fast_cutoff,
            inter_frame_slow_cutoff=self.inter_frame_slow_cutoff,
            inter_frame_deviation_time_const=self.inter_frame_deviation_time_const,
            inter_output_time_const=self.inter_output_time_const,
            inter_frame_presence_timeout=self.inter_frame_presence_timeout,
            # inter_phase_boost is removed
        )


presence_zone_config_timeline = (
    tm.start(_PresenceZoneConfig_v0)
    .load(str, _PresenceZoneConfig_v0.from_json, fail=[TypeError])
    .load(dict, _PresenceZoneConfig_v0.from_dict, fail=[TypeError])
    .nop()
    .epoch(PresenceZoneConfig, _PresenceZoneConfig_v0.migrate, fail=[])
    .load(str, PresenceZoneConfig.from_json, fail=[TypeError])
    .load(dict, PresenceZoneConfig.from_dict, fail=[TypeError])
)


presence_wake_up_config_timeline = (
    tm.start(_PresenceWakeUpConfig_v0)
    .load(str, _PresenceWakeUpConfig_v0.from_json, fail=[TypeError])
    .load(dict, _PresenceWakeUpConfig_v0.from_dict, fail=[TypeError])
    .nop()
    .epoch(PresenceWakeUpConfig, _PresenceWakeUpConfig_v0.migrate, fail=[])
    .load(str, PresenceWakeUpConfig.from_json, fail=[TypeError])
    .load(dict, PresenceWakeUpConfig.from_dict, fail=[TypeError])
)
