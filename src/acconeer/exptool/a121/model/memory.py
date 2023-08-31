# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import numpy as np

from acconeer.exptool.a121 import SensorConfig, SessionConfig
from acconeer.exptool.a121._core import utils as core_utils
from acconeer.exptool.a121.algo import get_distance_filter_edge_margin
from acconeer.exptool.a121.algo.distance import (
    Detector as DistanceDetector,
)
from acconeer.exptool.a121.algo.distance import (
    DetectorConfig as DistanceConfig,
)
from acconeer.exptool.a121.algo.distance import (
    MeasurementType,
    ThresholdMethod,
)


OVERHEAD = 68
CALIB_BUFFER = 3452
BYTES_PER_POINT = 4
MAX_NUM_POINTS = 4095

RSS_HEAP_PER_SUBSWEEP = 232
RSS_HEAP_PER_SENSOR = 512
RSS_HEAP_PER_CONFIG = 472

SIZE_OF_FLOAT = 4

DISTANCE_HEAP_OVERHEAD = 708
DISTANCE_HEAP_PER_PROCESSOR = 224


def _sweep_external_heap_memory(config: SensorConfig) -> int:
    total_num_points = (
        np.sum([subconfig.num_points for subconfig in config.subsweeps]) * config.sweeps_per_frame
    )

    total_bytes = max(total_num_points * BYTES_PER_POINT, CALIB_BUFFER) + OVERHEAD

    return int(total_bytes)


def _sweep_rss_heap_memory(config: SensorConfig) -> int:
    return RSS_HEAP_PER_CONFIG + config.num_subsweeps * RSS_HEAP_PER_SUBSWEEP


def session_external_heap_memory(config: SessionConfig) -> int:
    sensor_cfgs = list(core_utils.iterate_extended_structure_values(config.groups))

    return max([_sweep_external_heap_memory(cfg) for cfg in sensor_cfgs])


def _session_config_rss_heap_memory(config: SessionConfig) -> int:
    sensor_cfgs = list(core_utils.iterate_extended_structure_values(config.groups))

    return sum([_sweep_rss_heap_memory(cfg) for cfg in sensor_cfgs])


def session_rss_heap_memory(config: SessionConfig) -> int:
    sensor_ids = set([x[1] for x in core_utils.iterate_extended_structure(config.groups)])

    return RSS_HEAP_PER_SENSOR * len(sensor_ids) + _session_config_rss_heap_memory(config)


def session_heap_memory(config: SessionConfig) -> int:
    return session_external_heap_memory(config) + session_rss_heap_memory(config)


def distance_external_heap_memory(config: DistanceConfig) -> int:
    offset_sensor_config = DistanceDetector._get_calibrate_offset_sensor_config()
    (
        session_config,
        processor_specs,
    ) = DistanceDetector._detector_to_session_config_and_processor_specs(config, [1])
    noise_session_config = DistanceDetector._get_calibrate_noise_session_config(
        session_config, [1]
    )

    offset_ext_heap = session_external_heap_memory(SessionConfig(offset_sensor_config))
    session_ext_heap = session_external_heap_memory(session_config)
    noise_ext_heap = session_external_heap_memory(noise_session_config)

    sensor_buffer = max([offset_ext_heap, session_ext_heap, noise_ext_heap])

    NOISE_NUM_POINTS = 220
    FILTFILT_PAD_LEN = 9

    noise_work_buffer = (NOISE_NUM_POINTS + 2 * FILTFILT_PAD_LEN) * 2 * SIZE_OF_FLOAT

    sensor_cfgs = list(core_utils.iterate_extended_structure_values(session_config.groups))

    aggr_work_buffer = 0
    det_calib_buffer = 2 * SIZE_OF_FLOAT
    aggr_calib_buffer = 0

    for proc_spec in processor_specs:
        proc_work_buffer = 0
        proc_calib_buffer = 0
        sensor_cfg = sensor_cfgs[proc_spec.group_index]

        if proc_spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            subsweep_cfgs = [sensor_cfg.subsweeps[1]]
            det_calib_buffer += SIZE_OF_FLOAT
        else:
            subsweep_cfgs = [sensor_cfg.subsweeps[i] for i in proc_spec.subsweep_indexes]
            det_calib_buffer += len(subsweep_cfgs) * SIZE_OF_FLOAT

        num_points = sum([sub_cfg.num_points for sub_cfg in subsweep_cfgs])
        filt_margin = get_distance_filter_edge_margin(
            subsweep_cfgs[0].profile, subsweep_cfgs[0].step_length
        )
        num_points_cropped = num_points - 2 * filt_margin
        half_num_points_cropped = num_points_cropped // 2
        aligned_half_num_points_cropped = (
            half_num_points_cropped
            if half_num_points_cropped % 2 == 0
            else half_num_points_cropped + 1
        )

        proc_work_buffer = (num_points + 2 * FILTFILT_PAD_LEN) * 2 * SIZE_OF_FLOAT
        proc_work_buffer += ((num_points_cropped + (32 - 1)) // 32) * SIZE_OF_FLOAT
        proc_work_buffer += aligned_half_num_points_cropped * 2

        if proc_spec.processor_config.threshold_method == ThresholdMethod.RECORDED:
            proc_calib_buffer += num_points_cropped * SIZE_OF_FLOAT * 3
            proc_calib_buffer += len(subsweep_cfgs) * SIZE_OF_FLOAT

        if proc_spec.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            proc_calib_buffer += sensor_cfg.sweeps_per_frame * num_points * SIZE_OF_FLOAT
            proc_calib_buffer += sensor_cfg.sweeps_per_frame * SIZE_OF_FLOAT

        aggr_work_buffer += proc_work_buffer
        aggr_calib_buffer += proc_calib_buffer

    work_buffer = max([noise_work_buffer, aggr_work_buffer])

    return sensor_buffer + work_buffer + det_calib_buffer + aggr_calib_buffer


def distance_rss_heap_memory(config: DistanceConfig) -> int:
    offset_sensor_config = DistanceDetector._get_calibrate_offset_sensor_config()
    (
        session_config,
        processor_configs,
    ) = DistanceDetector._detector_to_session_config_and_processor_specs(config, [1])
    noise_session_config = DistanceDetector._get_calibrate_noise_session_config(
        session_config, [1]
    )

    offset_rss_heap = _session_config_rss_heap_memory(SessionConfig(offset_sensor_config))
    session_rss_heap = _session_config_rss_heap_memory(session_config)
    noise_rss_heap = _session_config_rss_heap_memory(noise_session_config)

    # Loopback sweep is not part of noise calibration
    if DistanceDetector._has_close_range_measurement(config):
        noise_rss_heap = noise_rss_heap - RSS_HEAP_PER_SUBSWEEP

    sensor_heap = RSS_HEAP_PER_SENSOR

    processor_heap = DISTANCE_HEAP_PER_PROCESSOR * len(processor_configs)

    return (
        DISTANCE_HEAP_OVERHEAD
        + processor_heap
        + sensor_heap
        + offset_rss_heap
        + session_rss_heap
        + noise_rss_heap
    )


def distance_heap_memory(config: DistanceConfig) -> int:
    return distance_external_heap_memory(config) + distance_rss_heap_memory(config)
