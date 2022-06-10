from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance._processors import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
)


@attrs.frozen(kw_only=True)
class ProcessorSpec:
    processor_config: ProcessorConfig = attrs.field()
    group_index: int = attrs.field()
    sensor_id: int = attrs.field()
    subsweep_indexes: list[int] = attrs.field()
    processor_context: Optional[ProcessorContext] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class AggregatorConfig:

    pass


@attrs.frozen(kw_only=True)
class AggregatorResult:

    pass


class Aggregator:
    """Aggregating class

    Instantiates Processor objects based configuration from Detector.

    Aggregates result, based on selected peak sorting strategy, from underlying Processor objects.
    """

    def __init__(
        self,
        session_config: a121.SessionConfig,
        extended_metadata: list[dict[int, a121.Metadata]],
        aggregator_config: AggregatorConfig,
        specs: list[ProcessorSpec],
    ):
        self.aggregator_config = aggregator_config

        self.processors: list[Processor] = []

        for spec in specs:
            metadata = extended_metadata[spec.group_index][spec.sensor_id]
            sensor_config = session_config.groups[spec.group_index][spec.sensor_id]

            processor = Processor(
                sensor_config=sensor_config,
                metadata=metadata,
                processor_config=spec.processor_config,
                subsweep_indexes=spec.subsweep_indexes,
                context=spec.processor_context,
            )
            self.processors.append(processor)

    def process(self, extended_result: list[dict[int, a121.Result]]) -> AggregatorResult:
        pass
