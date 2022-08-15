# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
from attr import Attribute

from acconeer.exptool import a121
from acconeer.exptool.a121._core.utils import is_divisor_of, is_multiple_of
from acconeer.exptool.a121.algo import AlgoConfigBase

from ._processors import Processor, ProcessorConfig, ProcessorExtraResult


SPARSE_IQ_PPC = 24


@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=1.0)
    end_m: float = attrs.field(default=2.0)
    step_length: Optional[int] = attrs.field(default=None)
    detection_threshold: float = attrs.field(default=1.5)
    frame_rate: float = attrs.field(default=10.0)
    sweeps_per_frame: int = attrs.field(default=16)
    hwaas: int = attrs.field(default=32)

    @step_length.validator
    def _validate_step_length(self, attrs: Attribute, step_length: int) -> None:
        if step_length is not None:
            if not (
                is_divisor_of(SPARSE_IQ_PPC, step_length)
                or is_multiple_of(SPARSE_IQ_PPC, step_length)
            ):
                raise ValueError(f"step_length must be a divisor or multiple of {SPARSE_IQ_PPC}")


@attrs.frozen(kw_only=True)
class DetectorResult:
    presence_score: float = attrs.field()
    presence_distance: float = attrs.field()
    presence_detected: bool = attrs.field()
    processor_extra_result: ProcessorExtraResult = attrs.field()
    service_result: a121.Result = attrs.field()

    def __str__(self) -> str:
        s = "Presence! " if self.presence_detected else "No presence. "
        s += f"Score {self.presence_score:.3f} at {self.presence_distance:.3f} m "
        return s


class Detector:
    MIN_DIST_M = {
        a121.Profile.PROFILE_1: None,
        a121.Profile.PROFILE_2: 0.28,
        a121.Profile.PROFILE_3: 0.56,
        a121.Profile.PROFILE_4: 0.76,
        a121.Profile.PROFILE_5: 1.28,
    }

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

    def start(self, recorder: Optional[a121.Recorder] = None) -> None:
        if self.started:
            raise RuntimeError("Already started")

        sensor_config = self._get_sensor_config(self.detector_config)
        session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        metadata = self.client.setup_session(session_config)
        assert isinstance(metadata, a121.Metadata)

        processor_config = self._get_processor_config(self.detector_config)

        self.processor = Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
        )

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("presence_detector")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.detector_config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        self.client.start_session(recorder)

        self.started = True

    @classmethod
    def _get_sensor_config(cls, detector_config: DetectorConfig) -> a121.SensorConfig:
        start_point = int(np.floor(detector_config.start_m / Processor.APPROX_BASE_STEP_LENGTH_M))
        viable_profiles = [
            k for k, v in cls.MIN_DIST_M.items() if v is None or v <= detector_config.start_m
        ]
        profile = viable_profiles[-1]

        if detector_config.step_length is not None:
            step_length = detector_config.step_length
        else:
            fwhm_p = Processor.ENVELOPE_FWHM_M[profile] / Processor.APPROX_BASE_STEP_LENGTH_M
            step_length = int((fwhm_p // SPARSE_IQ_PPC) * SPARSE_IQ_PPC)

        num_point = int(
            np.ceil(
                (detector_config.end_m - detector_config.start_m)
                / (step_length * Processor.APPROX_BASE_STEP_LENGTH_M)
            )
        )
        return a121.SensorConfig(
            profile=profile,
            start_point=start_point,
            num_points=num_point,
            step_length=step_length,
            hwaas=detector_config.hwaas,
            sweeps_per_frame=detector_config.sweeps_per_frame,
            frame_rate=detector_config.frame_rate,
        )

    @classmethod
    def _get_processor_config(cls, detector_config: DetectorConfig) -> ProcessorConfig:
        return ProcessorConfig(
            detection_threshold=detector_config.detection_threshold,
        )

    def get_next(self) -> DetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return DetectorResult(
            presence_score=processor_result.presence_score,
            presence_distance=processor_result.presence_distance,
            presence_detected=processor_result.presence_detected,
            processor_extra_result=processor_result.extra_result,
            service_result=result,
        )

    def update_config(self, config: DetectorConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            raise RuntimeError("Already stopped")

        recorder_result = self.client.stop_session()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    detector_config: DetectorConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )
    algo_group.create_dataset(
        "detector_config",
        data=detector_config.to_json(),
        dtype=a121._H5PY_STR_DTYPE,
        track_times=False,
    )


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, DetectorConfig]:
    sensor_id = algo_group["sensor_id"][()]
    config = DetectorConfig.from_json(algo_group["detector_config"][()])
    return sensor_id, config
