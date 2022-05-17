from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool import a121


class DistanceDetectorConfig:
    pass


@attrs.frozen(kw_only=True)
class DistanceDetectorResult:
    distance: Optional[float] = attrs.field()


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

    def calibrate(self) -> None:
        ...

    def execute_background_measurement(self) -> None:
        ...

    def start(self) -> None:
        ...

    def get_next(self) -> DistanceDetectorResult:
        ...

    def update_config(self, config: DistanceDetectorConfig) -> None:
        ...

    def stop(self) -> None:
        ...
