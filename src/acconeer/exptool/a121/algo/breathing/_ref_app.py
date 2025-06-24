# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
from attributes_doc import attributes_doc

from acconeer.exptool import a121
from acconeer.exptool import type_migration as tm
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    AlgoConfigBase,
    Controller,
)
from acconeer.exptool.a121.algo.breathing._processor import (
    AppState,
    BreathingProcessorConfig,
    BreathingProcessorResult,
    Processor,
    ProcessorConfig,
)
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig
from acconeer.exptool.a121.algo.presence import ProcessorResult as PresenceProcessorResult
from acconeer.exptool.a121.algo.presence._processors import processor_config_timeline


def get_presence_config() -> PresenceProcessorConfig:
    presence_config = PresenceProcessorConfig()
    presence_config.intra_detection_threshold = 4.0
    return presence_config


@attributes_doc
@attrs.mutable(kw_only=True)
class RefAppConfig(AlgoConfigBase):
    use_presence_processor: bool = attrs.field(default=True)
    """If True, use the presence processor to determine distance to subject."""

    num_distances_to_analyze: int = attrs.field(default=3)
    """Indicates the number of distance to analyzed, centered around the distance where presence
    is detected."""

    distance_determination_duration: float = attrs.field(default=5.0)
    """Time for the presence processor to determine distance to presence."""

    start_m: float = attrs.field(default=0.3)
    """Start of measurement range (m)."""

    end_m: float = attrs.field(default=1.5)
    """End of measurement range (m)."""

    hwaas: int = attrs.field(default=32)
    """HWAAS."""

    profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_3, converter=a121.Profile)
    """Profile."""

    frame_rate: float = attrs.field(default=20.0)
    """Frame rate."""

    sweeps_per_frame: int = attrs.field(default=16)
    """Sweeps per frame."""

    breathing_config: BreathingProcessorConfig = attrs.field(factory=BreathingProcessorConfig)
    """Breathing configuration."""

    presence_config: PresenceProcessorConfig = attrs.field(factory=get_presence_config)
    """Presence configuration."""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RefAppConfig:
        presence_dict = d["presence_config"]
        if presence_dict is not None:
            try:
                d["presence_config"] = processor_config_timeline.migrate(presence_dict)
            except tm.core.MigrationErrorGroup as exc:
                raise TypeError() from exc

        breathing_dict = d["breathing_config"]
        if breathing_dict is not None:
            d["breathing_config"] = BreathingProcessorConfig.from_dict(breathing_dict)
        return cls(**d)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if self.end_m < self.start_m:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "end_m",
                    "End point must be greater than start point",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class RefAppResult:
    app_state: AppState
    """Application state."""

    distances_being_analyzed: Optional[Tuple[int, int]] = None
    """Range where breathing is being analyzed."""

    presence_result: PresenceProcessorResult
    """Presence processor result."""

    breathing_result: Optional[BreathingProcessorResult] = attrs.field(default=None)
    """Breathing processor result."""


class RefApp(Controller[RefAppConfig, RefAppResult]):
    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        ref_app_config: RefAppConfig,
    ) -> None:
        super().__init__(client=client, config=ref_app_config)

        self.sensor_config = get_sensor_config(ref_app_config)

        self.processor_config = ProcessorConfig()
        self.processor_config.num_distances_to_analyze = ref_app_config.num_distances_to_analyze
        self.processor_config.distance_determination_duration = (
            ref_app_config.distance_determination_duration
        )
        self.processor_config.use_presence_processor = ref_app_config.use_presence_processor
        self.processor_config.presence_config = ref_app_config.presence_config
        self.processor_config.breathing_config = ref_app_config.breathing_config

        self.sensor_id = sensor_id

        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        self.metadata = self.client.setup_session(
            a121.SessionConfig({self.sensor_id: self.sensor_config})
        )

        assert not isinstance(self.metadata, list)

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("breathing")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

            self.client.attach_recorder(recorder)

        self.processor = Processor(
            sensor_config=self.sensor_config,
            processor_config=self.processor_config,
            metadata=self.metadata,
        )

        self.client.start_session()

        self.started = True

    def get_next(self) -> RefAppResult:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        result = self.client.get_next()
        assert not isinstance(result, list)

        processor_result = self.processor.process(result)

        ref_app_result = RefAppResult(
            app_state=processor_result.app_state,
            distances_being_analyzed=processor_result.distances_being_analyzed,
            breathing_result=processor_result.breathing_result,
            presence_result=processor_result.presence_result,
        )

        return ref_app_result

    def stop(self) -> Any:
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


def _determine_step_length(ref_app_config: RefAppConfig) -> int:
    # Determine step length based on selected profile. The target length is half FWHM.
    VALID_STEP_LENGTHS = [1, 2, 4, 6, 8, 12, 24]
    step_length = int(
        ENVELOPE_FWHM_M[a121.Profile(ref_app_config.profile)] / APPROX_BASE_STEP_LENGTH_M / 2
    )

    if step_length < VALID_STEP_LENGTHS[-1]:
        idx_closest = np.sum(np.array(VALID_STEP_LENGTHS) <= step_length) - 1
        step_length = int(VALID_STEP_LENGTHS[idx_closest])
    else:
        step_length = int((step_length // VALID_STEP_LENGTHS[-1]) * VALID_STEP_LENGTHS[-1])

    return step_length


def get_sensor_config(ref_app_config: RefAppConfig) -> a121.SensorConfig:
    """Defines sensor configuration based on reference application configuration."""
    step_length = _determine_step_length(ref_app_config)

    start_point = int(ref_app_config.start_m // APPROX_BASE_STEP_LENGTH_M)
    num_points = int(
        np.ceil(
            (ref_app_config.end_m - ref_app_config.start_m)
            / (step_length * APPROX_BASE_STEP_LENGTH_M)
        )
        + 1
    )

    c = a121.SensorConfig()
    c.start_point = start_point
    c.num_points = num_points
    c.step_length = step_length
    c.hwaas = ref_app_config.hwaas
    c.profile = ref_app_config.profile
    c.sweeps_per_frame = ref_app_config.sweeps_per_frame
    c.frame_rate = ref_app_config.frame_rate

    return c
