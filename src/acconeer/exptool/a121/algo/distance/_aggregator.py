from __future__ import annotations

from typing import List, Optional

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance._processors import ProcessorConfig, ProcessorContext


@attrs.frozen(kw_only=True)
class ProcessorArgs:
    sensor_config: a121.SensorConfig = attrs.field()
    metadata: a121.Metadata = attrs.field()
    processor_config: ProcessorConfig = attrs.field()
    subsweep_indexes: Optional[List[int]] = attrs.field(default=None)
    context: Optional[ProcessorContext] = attrs.field(default=None)


class Aggregator:
    """Aggregating processor

    Instantiates Processor objects based configuration from Detector.

    Aggregates result, based on selected peak sorting strategy, from underlying Processor objects.
    """

    def __init__(self):
        pass
