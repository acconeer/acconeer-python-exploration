from __future__ import annotations

import attrs
import numpy as np

from acconeer.exptool import a121

from ._processors import Processor, ProcessorConfig


@attrs.frozen(kw_only=True)
class DetectorConfig:
    start_m: float = attrs.field()
    end_m: float = attrs.field()
    detection_threshold: float = attrs.field(default=1.5)


@attrs.frozen(kw_only=True)
class DetectorResult:
    presence_score: float = attrs.field()
    presence_distance: float = attrs.field()
    presence_detected: bool = attrs.field()


class Detector:
    APPROX_BASE_STEP_LENGTH_M = 2.5e-3

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

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Already started")

        sensor_config = self._get_sensor_config(self.detector_config)
        session_config = a121.SessionConfig(
            sensor_config,
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

        self.client.start_session()

        self.started = True

    @classmethod
    def _get_sensor_config(cls, detector_config: DetectorConfig) -> a121.SensorConfig:
        step_length = 24
        start_point = int(np.floor(detector_config.start_m / cls.APPROX_BASE_STEP_LENGTH_M))
        num_point = int(
            np.ceil(
                (detector_config.end_m - detector_config.start_m)
                / (step_length * cls.APPROX_BASE_STEP_LENGTH_M)
            )
        )
        return a121.SensorConfig(
            start_point=start_point,
            num_points=num_point,
            step_length=step_length,
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
        )

    def update_config(self, config: DetectorConfig) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        if not self.started:
            raise RuntimeError("Already stopped")

        self.client.stop_session()

        self.started = False
