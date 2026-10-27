# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Heap memory model for A2

Follows the allocations of the SDK example applications. RSS allocates the config and
processing handle (RSS heap). The application allocates the radar buffer and the heatmap
processor buffers (external heap). Struct sizes come from the APS build of the examples.
"""

from __future__ import annotations

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap import capon, coherent, conventional, robust_capon
from acconeer.exptool.a2.algo.heatmap.config_common import HeatmapConfigCommon


SIZE_OF_FLOAT = 4
SIZE_OF_COMPLEX_FLOAT = 8
SIZE_OF_POINTER = 4
SIZE_OF_UINT32 = 4
# A point is one acc_int16_complex_t
BYTES_PER_POINT = 4

RS_PACKET_SIZE = 64
FRAME_BUFFER_ALIGNMENT = 4
PROCESSOR_ALIGNMENT = 8
MIN_CALIBRATION_BUFFER_SIZE = 448

RSS_HEAP_PER_CONFIG = 196
RSS_HEAP_PER_PROCESSING_HANDLE = 8
MEASURE_RESULTS_CONTEXT_SIZE = 80

# The loopback subsweep RSS appends is one point on one Tx and one Rx
JITTER_COMPENSATION_SUBSWEEP_SIZE = BYTES_PER_POINT

NOISE_SWEEPS_PER_FRAME = 1
NOISE_N_WANTED_SAMPLES = 100
ROBUST_CAPON_NOISE_SWEEPS_PER_FRAME = 3
ROBUST_CAPON_NOISE_N_WANTED_SAMPLES = 900

COVARIANCE_MATRIX_INFO_SIZE = 12
TIME_FILTER_INFO_SIZE = 16
AMP_FILTER_STATE_SIZE = 2

HEATMAP_CAPON_CONFIG_SIZE = 44
HEATMAP_CAPON_INFO_SIZE = 20
HEATMAP_CONVENTIONAL_CONFIG_SIZE = 48
HEATMAP_CONVENTIONAL_INFO_SIZE = 24
HEATMAP_COHERENT_CONFIG_SIZE = 44
HEATMAP_COHERENT_INFO_SIZE = 20
HEATMAP_ROBUST_CAPON_CONFIG_SIZE = 56
HEATMAP_ROBUST_CAPON_INFO_SIZE = 56


def _align(size: int, alignment: int) -> int:
    return (size + alignment - 1) // alignment * alignment


def _count_bits(mask: int) -> int:
    return bin(mask).count("1")


def _frame_buffer_size(
    subsweep_sizes: list[int], sweeps_per_frame: int, jitter_compensation: bool
) -> int:
    """Jitter compensation adds a loopback subsweep. The last subsweep fills whole packets."""
    if jitter_compensation:
        subsweep_sizes = [*subsweep_sizes, JITTER_COMPENSATION_SUBSWEEP_SIZE]

    size = (sweeps_per_frame - 1) * sum(subsweep_sizes)
    size += sum(subsweep_sizes[:-1])
    size += _align(subsweep_sizes[-1], RS_PACKET_SIZE)

    return _align(size, FRAME_BUFFER_ALIGNMENT)


def _radar_buffer_size(
    subsweep_sizes: list[int], sweeps_per_frame: int, jitter_compensation: bool
) -> int:
    """The buffer size RSS asks the application to allocate"""
    size = MEASURE_RESULTS_CONTEXT_SIZE + _frame_buffer_size(
        subsweep_sizes, sweeps_per_frame, jitter_compensation
    )

    return max(size, MIN_CALIBRATION_BUFFER_SIZE)


def _subsweep_data_size(subsweep: a2.SubsweepConfig) -> int:
    return subsweep.num_points * subsweep.num_channels * BYTES_PER_POINT


def _sensor_config_buffer_size(config: a2.SensorConfig) -> int:
    return _radar_buffer_size(
        [_subsweep_data_size(subsweep) for subsweep in config.subsweeps],
        config.sweeps_per_frame,
        config.jitter_compensation,
    )


def session_rss_heap_memory(config: a2.SessionConfig) -> int:
    return len(config.sensor_configs) * (RSS_HEAP_PER_CONFIG + RSS_HEAP_PER_PROCESSING_HANDLE)


def session_external_heap_memory(config: a2.SessionConfig) -> int:
    return max(
        _sensor_config_buffer_size(sensor_config) for sensor_config in config.sensor_configs
    )


def session_heap_memory(config: a2.SessionConfig) -> int:
    return session_external_heap_memory(config) + session_rss_heap_memory(config)


def _noise_normalization_buffer_size(
    config: a2.SensorConfig,
    sweeps_per_frame: int,
    n_wanted_samples: int,
    pool_noise_per_rx: bool,
) -> int:
    """The noise is measured with the radar config resized to the wanted sample count"""
    subsweep_sizes = []
    num_noise_estimates = 0

    for subsweep in config.subsweeps:
        denominator = sweeps_per_frame

        if pool_noise_per_rx:
            denominator *= _count_bits(subsweep.tx_antenna_mask)

        num_points = (n_wanted_samples + denominator - 1) // denominator
        subsweep_sizes.append(num_points * subsweep.num_channels * BYTES_PER_POINT)

        if pool_noise_per_rx:
            num_noise_estimates += _count_bits(subsweep.rx_antenna_mask)
        else:
            num_noise_estimates += subsweep.num_channels

    buffer_size = _radar_buffer_size(subsweep_sizes, sweeps_per_frame, config.jitter_compensation)

    noise_estimate_size = SIZE_OF_COMPLEX_FLOAT + SIZE_OF_FLOAT + SIZE_OF_UINT32

    return buffer_size + num_noise_estimates * noise_estimate_size


def _noise_values_size(config: a2.SensorConfig) -> int:
    num_values = sum(subsweep.num_points * subsweep.num_channels for subsweep in config.subsweeps)

    # Alignment slack, as in acc_noise_normalization_get_length
    return (num_values + SIZE_OF_POINTER - 1) * SIZE_OF_FLOAT


def _normalized_frame_size(config: a2.SensorConfig) -> int:
    subsweep = config.subsweep

    return (
        config.sweeps_per_frame
        * subsweep.num_points
        * subsweep.num_channels
        * SIZE_OF_COMPLEX_FLOAT
    )


def _time_filter_persistent_size(num_channels: int, num_points: int) -> int:
    size = _align(TIME_FILTER_INFO_SIZE, PROCESSOR_ALIGNMENT)
    size += num_channels * num_points * SIZE_OF_COMPLEX_FLOAT

    return _align(size, PROCESSOR_ALIGNMENT)


def _covariance_matrix_persistent_size(num_channels: int) -> int:
    off_diagonal_length = num_channels * (num_channels - 1) // 2

    size = _align(COVARIANCE_MATRIX_INFO_SIZE, PROCESSOR_ALIGNMENT)
    size = _align(size + num_channels * SIZE_OF_FLOAT, PROCESSOR_ALIGNMENT)
    size = _align(size + off_diagonal_length * SIZE_OF_COMPLEX_FLOAT, PROCESSOR_ALIGNMENT)

    return size


def _covariance_matrix_scratch_size(num_channels: int) -> int:
    return num_channels * num_channels * SIZE_OF_COMPLEX_FLOAT + num_channels * SIZE_OF_FLOAT


def _num_angle_points(subsweep: a2.SubsweepConfig, heatmap_config: HeatmapConfigCommon) -> int:
    return heatmap_config.num_az_angles * heatmap_config.num_el_angles * subsweep.num_points


def _steering_vectors_size(
    subsweep: a2.SubsweepConfig, heatmap_config: HeatmapConfigCommon
) -> int:
    return (
        heatmap_config.num_az_angles
        * heatmap_config.num_el_angles
        * subsweep.num_channels
        * SIZE_OF_COMPLEX_FLOAT
    )


def _heatmap_external_heap_memory(
    session_config: a2.SessionConfig,
    heatmap_config: HeatmapConfigCommon,
    scratch_size: int,
    persistent_size: int,
    noise_sweeps_per_frame: int = NOISE_SWEEPS_PER_FRAME,
    noise_n_wanted_samples: int = NOISE_N_WANTED_SAMPLES,
    pool_noise_per_rx: bool = False,
) -> int:
    """The radar buffer is shared with the noise measurement

    The heatmap processors take a single subsweep, so this raises an
    AttributeError for a config carrying more than one.
    """
    sensor_config = session_config.sensor_config

    radar_buffer_size = max(
        _sensor_config_buffer_size(sensor_config),
        _noise_normalization_buffer_size(
            sensor_config, noise_sweeps_per_frame, noise_n_wanted_samples, pool_noise_per_rx
        ),
    )

    return (
        radar_buffer_size
        + _noise_values_size(sensor_config)
        + _normalized_frame_size(sensor_config)
        + scratch_size
        + persistent_size
        + _steering_vectors_size(sensor_config.subsweep, heatmap_config)
    )


def heatmap_capon_rss_heap_memory(session_config: a2.SessionConfig) -> int:
    return session_rss_heap_memory(session_config) + HEATMAP_CAPON_CONFIG_SIZE


def heatmap_capon_external_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: capon.HeatmapConfig
) -> int:
    subsweep = session_config.sensor_config.subsweep
    num_channels = subsweep.num_channels
    num_points = subsweep.num_points

    persistent_size = _align(HEATMAP_CAPON_INFO_SIZE, PROCESSOR_ALIGNMENT)
    persistent_size += _time_filter_persistent_size(num_channels, num_points)
    persistent_size += num_points * _covariance_matrix_persistent_size(num_channels)

    scratch_size = _covariance_matrix_scratch_size(num_channels)
    scratch_size += _num_angle_points(subsweep, heatmap_config) * SIZE_OF_FLOAT

    return _heatmap_external_heap_memory(
        session_config, heatmap_config, scratch_size, persistent_size
    )


def heatmap_capon_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: capon.HeatmapConfig
) -> int:
    return heatmap_capon_external_heap_memory(
        session_config, heatmap_config
    ) + heatmap_capon_rss_heap_memory(session_config)


def heatmap_conventional_rss_heap_memory(session_config: a2.SessionConfig) -> int:
    return session_rss_heap_memory(session_config) + HEATMAP_CONVENTIONAL_CONFIG_SIZE


def heatmap_conventional_external_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: conventional.HeatmapConfig
) -> int:
    subsweep = session_config.sensor_config.subsweep
    num_channels = subsweep.num_channels
    num_points = subsweep.num_points

    persistent_size = _align(HEATMAP_CONVENTIONAL_INFO_SIZE, PROCESSOR_ALIGNMENT)

    if heatmap_config.heatmap_mode == conventional.HeatmapConfig.HeatmapMode.MOVEMENT:
        persistent_size += _time_filter_persistent_size(num_channels, num_points)

    persistent_size += num_points * _covariance_matrix_persistent_size(num_channels)

    scratch_size = _covariance_matrix_scratch_size(num_channels)
    scratch_size += _num_angle_points(subsweep, heatmap_config) * SIZE_OF_FLOAT

    return _heatmap_external_heap_memory(
        session_config, heatmap_config, scratch_size, persistent_size
    )


def heatmap_conventional_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: conventional.HeatmapConfig
) -> int:
    return heatmap_conventional_external_heap_memory(
        session_config, heatmap_config
    ) + heatmap_conventional_rss_heap_memory(session_config)


def heatmap_coherent_rss_heap_memory(session_config: a2.SessionConfig) -> int:
    return session_rss_heap_memory(session_config) + HEATMAP_COHERENT_CONFIG_SIZE


def heatmap_coherent_external_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: coherent.HeatmapConfig
) -> int:
    subsweep = session_config.sensor_config.subsweep
    num_channels = subsweep.num_channels
    num_points = subsweep.num_points

    persistent_size = _align(HEATMAP_COHERENT_INFO_SIZE, PROCESSOR_ALIGNMENT)

    if heatmap_config.heatmap_mode == coherent.HeatmapConfig.HeatmapMode.MOVEMENT:
        persistent_size += _time_filter_persistent_size(num_channels, num_points)

    persistent_size += num_points * num_channels * SIZE_OF_COMPLEX_FLOAT

    scratch_size = _num_angle_points(subsweep, heatmap_config) * SIZE_OF_COMPLEX_FLOAT

    return _heatmap_external_heap_memory(
        session_config, heatmap_config, scratch_size, persistent_size
    )


def heatmap_coherent_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: coherent.HeatmapConfig
) -> int:
    return heatmap_coherent_external_heap_memory(
        session_config, heatmap_config
    ) + heatmap_coherent_rss_heap_memory(session_config)


def heatmap_robust_capon_rss_heap_memory(session_config: a2.SessionConfig) -> int:
    return session_rss_heap_memory(session_config) + HEATMAP_ROBUST_CAPON_CONFIG_SIZE


def heatmap_robust_capon_external_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: robust_capon.HeatmapConfig
) -> int:
    subsweep = session_config.sensor_config.subsweep
    num_channels = subsweep.num_channels
    num_points = subsweep.num_points
    num_angle_points = _num_angle_points(subsweep, heatmap_config)
    mean_sweep_size = num_points * num_channels * SIZE_OF_COMPLEX_FLOAT

    persistent_size = _align(HEATMAP_ROBUST_CAPON_INFO_SIZE, PROCESSOR_ALIGNMENT)
    persistent_size += _time_filter_persistent_size(num_channels, num_points)
    persistent_size += num_points * _covariance_matrix_persistent_size(num_channels)
    persistent_size += num_points * num_channels * num_channels * SIZE_OF_COMPLEX_FLOAT
    persistent_size += mean_sweep_size
    # The spatial branch is reserved regardless of config
    persistent_size += _time_filter_persistent_size(num_channels, num_points)
    persistent_size += mean_sweep_size
    # Only the float32 arrays can break the alignment
    persistent_size += (
        _align(AMP_FILTER_STATE_SIZE, PROCESSOR_ALIGNMENT) + num_points * SIZE_OF_FLOAT
    )
    persistent_size = _align(persistent_size, PROCESSOR_ALIGNMENT)
    persistent_size += num_angle_points * SIZE_OF_FLOAT
    persistent_size = _align(persistent_size, PROCESSOR_ALIGNMENT)

    scratch_size = 3 * num_channels * num_channels * SIZE_OF_COMPLEX_FLOAT
    scratch_size += num_channels * SIZE_OF_FLOAT
    scratch_size += _covariance_matrix_scratch_size(num_channels)
    scratch_size += num_angle_points * SIZE_OF_FLOAT

    return _heatmap_external_heap_memory(
        session_config,
        heatmap_config,
        scratch_size,
        persistent_size,
        noise_sweeps_per_frame=ROBUST_CAPON_NOISE_SWEEPS_PER_FRAME,
        noise_n_wanted_samples=ROBUST_CAPON_NOISE_N_WANTED_SAMPLES,
        pool_noise_per_rx=True,
    )


def heatmap_robust_capon_heap_memory(
    session_config: a2.SessionConfig, heatmap_config: robust_capon.HeatmapConfig
) -> int:
    return heatmap_robust_capon_external_heap_memory(
        session_config, heatmap_config
    ) + heatmap_robust_capon_rss_heap_memory(session_config)
