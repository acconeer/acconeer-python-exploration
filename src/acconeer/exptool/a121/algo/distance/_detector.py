from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool import a121

from ._processors import Processor, ProcessorConfig, ProcessorMode


@attrs.frozen(kw_only=True)
class DetectorConfig:
    pass


@attrs.frozen(kw_only=True)
class DetectorResult:
    distances: Optional[list[float]] = attrs.field(default=None)


class Detector:
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
        self.processor: Optional[Processor] = None

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

        processor_config = ProcessorConfig(
            processor_mode=ProcessorMode.DISTANCE_ESTIMATION,
        )

        self.processor = Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
        )

        self.client.start_session()

        self.started = True

    def get_next(self) -> DetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return DetectorResult(
            distances=processor_result.estimated_distances,
        )

    def update_config(self, config: DetectorConfig) -> None:
        ...

    def stop(self) -> None:
        if not self.started:
            raise RuntimeError("Already stopped")

        self.client.stop_session()

        self.processor = None
        self.started = False
