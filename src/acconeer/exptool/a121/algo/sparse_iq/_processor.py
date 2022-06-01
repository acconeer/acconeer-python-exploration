from __future__ import annotations

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import Processor


@attrs.frozen(kw_only=True)
class SparseIQProcessorConfig:
    pass


@attrs.frozen(kw_only=True)
class SparseIQProcessorResult:
    pass


class SparseIQProcessor(Processor[SparseIQProcessorConfig, SparseIQProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: SparseIQProcessorConfig,
    ) -> None:
        ...

    def process(self, result: a121.Result) -> SparseIQProcessorResult:
        ...

        return SparseIQProcessorResult()

    def update_config(self, config: SparseIQProcessorConfig) -> None:
        ...
