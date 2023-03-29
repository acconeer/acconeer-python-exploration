# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities.configs.config_enums import IdleState, Profile
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo.presence._detector import Controller, Detector, DetectorConfig

from ._processor import Processor, ProcessorConfig


SPARSE_IQ_PPC = 24


def optional_profile_converter(profile: Optional[Profile]) -> Optional[Profile]:
    if profile is None:
        return None

    return Profile(profile)


def idle_state_converter(idle_state: IdleState) -> IdleState:
    return IdleState(idle_state)


@attrs.mutable(kw_only=True)
class RefAppConfig(DetectorConfig):
    num_zones: int = attrs.field(default=7)
    """Maximum number of detection zones."""

    show_all_detected_zones: bool = attrs.field(default=False)


@attrs.frozen(kw_only=True)
class RefAppResult:
    zone_limits: npt.NDArray[np.float_] = attrs.field()
    "The upper limit for each zone."

    presence_detected: bool = attrs.field()
    """True if presence was detected, False otherwise."""

    max_presence_zone: Optional[int] = attrs.field()
    """The zone for maximum presence score if presence detected, else None."""

    total_zone_detections: npt.NDArray[np.int_] = attrs.field()
    """Detection result for all zones."""

    inter_presence_score: float = attrs.field()
    """A measure of the amount of slow motion detected."""

    inter_zone_detections: npt.NDArray[np.int_] = attrs.field()
    """Slow motion presence detection result for all zones."""

    max_inter_zone: Optional[int] = attrs.field()
    """The zone for maximum slow motion presence score if slow presence detected, else None."""

    intra_presence_score: float = attrs.field()
    """A measure of the amount of fast motion detected."""

    intra_zone_detections: npt.NDArray[np.int_] = attrs.field()
    """Fast motion presence detection result for all zones."""

    max_intra_zone: Optional[int] = attrs.field()
    """The zone for maximum fast motion presence score if fast presence detecte, else None."""


class RefApp(Controller[RefAppConfig, RefAppResult]):
    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        ref_app_config: RefAppConfig,
    ) -> None:
        super().__init__(client=client, config=ref_app_config)
        self.sensor_id = sensor_id

        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            raise RuntimeError("Already started")

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("smart_presence")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        detector_config = self._get_detector_config(self.config)

        self.detector = Detector(
            client=self.client, sensor_id=self.sensor_id, detector_config=detector_config
        )
        self.detector.start(recorder=recorder, _algo_group=algo_group)
        assert self.detector.detector_metadata is not None

        session_config = self.detector.session_config

        processor_config = ProcessorConfig(num_zones=self.config.num_zones)

        self.ref_app_processor = Processor(
            processor_config, detector_config, session_config, self.detector.detector_metadata
        )

        self.started = True

    @classmethod
    def _get_detector_config(cls, ref_app_config: RefAppConfig) -> DetectorConfig:
        return DetectorConfig(
            start_m=ref_app_config.start_m,
            end_m=ref_app_config.end_m,
            profile=ref_app_config.profile,
            step_length=ref_app_config.step_length,
            frame_rate=ref_app_config.frame_rate,
            sweeps_per_frame=ref_app_config.sweeps_per_frame,
            hwaas=ref_app_config.hwaas,
            inter_frame_idle_state=ref_app_config.inter_frame_idle_state,
            intra_enable=ref_app_config.intra_enable,
            intra_detection_threshold=ref_app_config.intra_detection_threshold,
            intra_frame_time_const=ref_app_config.intra_frame_time_const,
            intra_output_time_const=ref_app_config.intra_output_time_const,
            inter_enable=ref_app_config.inter_enable,
            inter_detection_threshold=ref_app_config.inter_detection_threshold,
            inter_frame_fast_cutoff=ref_app_config.inter_frame_fast_cutoff,
            inter_frame_slow_cutoff=ref_app_config.inter_frame_slow_cutoff,
            inter_frame_deviation_time_const=ref_app_config.inter_frame_deviation_time_const,
            inter_output_time_const=ref_app_config.inter_output_time_const,
            inter_phase_boost=ref_app_config.inter_phase_boost,
            inter_frame_presence_timeout=ref_app_config.inter_frame_presence_timeout,
        )

    def get_next(self) -> RefAppResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.detector.get_next()
        processor_result = self.ref_app_processor.process(result)

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
        )

    def update_config(self, config: DetectorConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            raise RuntimeError("Already stopped")

        recorder_result = self.detector.stop()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    ref_app_config: RefAppConfig,
) -> None:
    algo_group.create_dataset(
        "ref_app_sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "ref_app_config", ref_app_config.to_json())


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, RefAppConfig]:
    sensor_id = int(algo_group["ref_app_sensor_id"][()])
    config = RefAppConfig.from_json(algo_group["ref_app_config"][()])
    return sensor_id, config
