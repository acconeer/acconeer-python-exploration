from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool import a121

from ._processors import DistanceProcessor, DistanceProcessorConfig, ProcessorMode


@attrs.frozen(kw_only=True)
class DistanceDetectorConfig:
    pass


@attrs.frozen(kw_only=True)
class DistanceDetectorResult:
    distances: Optional[list[float]] = attrs.field(default=None)


class DistanceDetector:
    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        detector_config: DistanceDetectorConfig,
    ) -> None:
        self.client = client
        self.sensor_id = sensor_id
        self.detector_config = detector_config

        self.started = False
        self.processor: Optional[DistanceProcessor] = None

    def calibrate(self) -> None:
        ...

    def execute_background_measurement(self) -> None:
        ...

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Already started")

        # TODO:
        sensor_config = a121.SensorConfig()
        config_groups = [{self.sensor_id: sensor_config}]
        session_config = a121.SessionConfig(
            config_groups,
            extended=False,
        )

        metadata = self.client.setup_session(session_config)
        assert isinstance(metadata, a121.Metadata)

        processor_config = DistanceProcessorConfig(
            processor_mode=ProcessorMode.DISTANCE_ESTIMATION,
        )

        self.processor = DistanceProcessor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
        )

        self.client.start_session()

        self.started = True

    def get_next(self) -> DistanceDetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return DistanceDetectorResult(
            distances=processor_result.estimated_distances,
        )

    def update_config(self, config: DistanceDetectorConfig) -> None:
        ...

    def stop(self) -> None:
        if not self.started:
            raise RuntimeError("Already stopped")

        self.client.stop_session()

        self.processor = None
        self.started = False
