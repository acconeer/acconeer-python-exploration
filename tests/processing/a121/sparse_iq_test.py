# Copyright (c) Acconeer AB, 2022
# All rights reserved

import functools

import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import sparse_iq
from acconeer.exptool.a121.algo.sparse_iq._serializers import ProcessorResultListH5Serializer


_SERIALIZED_TEST_FIELDS = (
    "distance_velocity_map",
    "amplitudes",
    "phases",
    # ignored: "frame"
)
SparseIqResultH5Serializer = functools.partial(
    ProcessorResultListH5Serializer,
    fields=_SERIALIZED_TEST_FIELDS,
    allow_missing_fields=True,
)


def result_comparator(this: sparse_iq.ProcessorResult, other: sparse_iq.ProcessorResult) -> bool:
    for field in _SERIALIZED_TEST_FIELDS:
        # all tested fields (_SERIALIZED_TEST_FIELDS) are floats, which calls for "isclose"
        if not np.isclose(getattr(this, field), getattr(other, field)).all():
            return False
    return True


def sparse_iq_default(record: a121.H5Record) -> sparse_iq.Processor:
    return sparse_iq.Processor(
        sensor_config=record.session_config.sensor_config,
        processor_config=sparse_iq.ProcessorConfig(),
        metadata=utils.unextend(record.extended_metadata),
    )
