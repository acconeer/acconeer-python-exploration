# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import presence
from acconeer.exptool.a121.algo.presence._serializers import ProcessorResultListH5Serializer


PresenceResultH5Serializer = ProcessorResultListH5Serializer


def result_comparator(this: presence.ProcessorResult, other: presence.ProcessorResult) -> bool:
    return bool(
        np.isclose(this.inter_presence_score, other.inter_presence_score)
        and np.isclose(this.intra_presence_score, other.intra_presence_score)
        and this.presence_detected == other.presence_detected
        and np.isclose(this.presence_distance, other.presence_distance)
    )


def presence_default(record: a121.H5Record) -> presence.Processor:
    return presence.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=presence.ProcessorConfig(),
        metadata=utils.unextend(record.extended_metadata),
    )


def presence_timeout_3s(record: a121.H5Record) -> presence.Processor:
    processor_config = presence.ProcessorConfig()
    processor_config.inter_frame_presence_timeout = 3
    return presence.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )


def presence_timeout_2s_phase_boost(record: a121.H5Record) -> presence.Processor:
    processor_config = presence.ProcessorConfig()
    processor_config.inter_frame_presence_timeout = 2
    processor_config.inter_phase_boost = True
    return presence.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )
