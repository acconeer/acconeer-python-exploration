# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import presence
from acconeer.exptool.a121.algo.presence._configs import (
    get_long_range_config,
    get_medium_range_config,
    get_short_range_config,
)
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
        processor_config=presence.Detector._get_processor_config(get_medium_range_config()),
        metadata=utils.unextend(record.extended_metadata),
    )


def presence_short_range(record: a121.H5Record) -> presence.Processor:
    return presence.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=presence.Detector._get_processor_config(get_short_range_config()),
        metadata=utils.unextend(record.extended_metadata),
    )


def presence_long_range(record: a121.H5Record) -> presence.Processor:
    return presence.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=presence.Detector._get_processor_config(get_long_range_config()),
        metadata=utils.unextend(record.extended_metadata),
    )


def presence_medium_range_phase_boost_no_timeout(record: a121.H5Record) -> presence.Processor:
    processor_config = presence.Detector._get_processor_config(get_medium_range_config())
    processor_config.inter_frame_presence_timeout = 0
    processor_config.inter_phase_boost = True
    return presence.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=processor_config,
        metadata=utils.unextend(record.extended_metadata),
    )
