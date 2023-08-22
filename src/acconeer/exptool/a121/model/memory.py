# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import numpy as np

from acconeer.exptool.a121 import SensorConfig


OVERHEAD = 68
CALIB_BUFFER = 3452
BYTES_PER_POINT = 4
MAX_NUM_POINTS = 4095

RSS_HEAP_PER_SUBSWEEP = 232
RSS_HEAP_OVERHEAD = 984


def service_external_heap_memory(config: SensorConfig) -> int:
    total_num_points = (
        np.sum([subconfig.num_points for subconfig in config.subsweeps]) * config.sweeps_per_frame
    )

    total_bytes = max(total_num_points * BYTES_PER_POINT, CALIB_BUFFER) + OVERHEAD

    return int(total_bytes)


def service_rss_heap_memory(config: SensorConfig) -> int:
    return RSS_HEAP_OVERHEAD + config.num_subsweeps * RSS_HEAP_PER_SUBSWEEP


def service_heap_memory(config: SensorConfig) -> int:
    return service_external_heap_memory(config) + service_rss_heap_memory(config)
