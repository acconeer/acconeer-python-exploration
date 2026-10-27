# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import math
import typing as t
from pathlib import Path

import attrs
import pytest
import yaml

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap import capon, coherent, conventional, robust_capon
from acconeer.exptool.a2.algo.heatmap.config_common import HeatmapConfigCommon
from acconeer.exptool.a2.model import memory


RssHeapMemoryFunction = t.Callable[[a2.SessionConfig], int]
HeapMemoryFunction = t.Callable[[a2.SessionConfig, t.Any], int]

# The heatmap configs of the SDK example applications, in the fields that reach memory
_EXAMPLE_CAPON_CONFIG = capon.HeatmapConfig(
    antenna_array=a2.AntennaArray.AP212,
    covariance_matrix_time_constant_s=10.0,
    high_pass_filter_time_constant_s=20.0,
    az_angle_range=(-60.0, 60.0),
    num_az_angles=25,
    el_angle_range=(-45.0, 45.0),
    num_el_angles=19,
)
_EXAMPLE_CONVENTIONAL_CONFIG = conventional.HeatmapConfig(
    antenna_array=a2.AntennaArray.AP212,
    heatmap_mode=conventional.HeatmapConfig.HeatmapMode.DISTANCE,
    covariance_matrix_time_constant_s=10.0,
    high_pass_filter_time_constant_s=20.0,
    az_angle_range=(-60.0, 60.0),
    num_az_angles=25,
    el_angle_range=(0.0, 0.0),
    num_el_angles=1,
)
_EXAMPLE_COHERENT_CONFIG = coherent.HeatmapConfig(
    antenna_array=a2.AntennaArray.AP212,
    heatmap_mode=coherent.HeatmapConfig.HeatmapMode.DISTANCE,
    high_pass_filter_time_constant_s=1.5,
    az_angle_range=(-60.0, 60.0),
    num_az_angles=30,
    el_angle_range=(0.0, 0.0),
    num_el_angles=1,
)
_EXAMPLE_ROBUST_CAPON_CONFIG = robust_capon.HeatmapConfig(
    antenna_array=a2.AntennaArray.AP212,
    covariance_matrix_time_constant_s=10.0,
    high_pass_filter_time_constant_s=20.0,
    steering_vector_epsilon=0.1,
    az_angle_range=(-60.0, 60.0),
    num_az_angles=25,
    el_angle_range=(0.0, 0.0),
    num_el_angles=1,
)


@pytest.fixture
def a2_memory_usage(a2_memory_usage_path: Path) -> dict[str, t.Any]:
    with a2_memory_usage_path.open("r", encoding="utf-8") as f:
        memory_usage: dict[str, t.Any] = yaml.safe_load(f)

    return memory_usage


@pytest.fixture
def xv211_memory_usage(a2_memory_usage: dict[str, t.Any]) -> dict[str, t.Any]:
    return dict(a2_memory_usage["devices"]["xv211"])


@pytest.fixture
def deviation_criteria(a2_memory_usage: dict[str, t.Any]) -> float:
    """How far the reference is allowed to lag the firmware before it is regenerated

    It is the RSS repo's own maintenance budget, so a reference that has not been
    regenerated for a while can sit most of it away from the model.
    """
    return float(a2_memory_usage["settings"]["deviation_criteria"])


def _assert_close(heap: int, expected_heap: int, deviation_criteria: float) -> None:
    deviation = heap / expected_heap - 1

    assert math.isclose(heap, expected_heap, rel_tol=deviation_criteria), (
        f"model says {heap} B, reference says {expected_heap} B ({deviation:+.1%})"
    )


def _session_config(**sensor_config_kwargs: t.Any) -> a2.SessionConfig:
    return a2.SessionConfig(
        [a2.SensorConfig.single_subsweep(**sensor_config_kwargs)], update_rate=None
    )


def _example_session_config(sweeps_per_frame: int) -> a2.SessionConfig:
    """The radar config of the SDK example applications"""
    return _session_config(
        sweeps_per_frame=sweeps_per_frame,
        jitter_compensation=False,
        num_points=16,
        profile=a2.Profile.PROFILE_3,
        tx_antenna_mask=0b010,
        rx_antenna_mask=0b0011,
    )


def test_service_memory_model(
    xv211_memory_usage: dict[str, t.Any], deviation_criteria: float
) -> None:
    expected_heap = xv211_memory_usage["example_service_iq"]["internal_aps"]["heap"]
    session_config = _example_session_config(sweeps_per_frame=2)

    rss_heap = memory.session_rss_heap_memory(session_config)
    external_heap = memory.session_external_heap_memory(session_config)
    heap = memory.session_heap_memory(session_config)

    assert rss_heap + external_heap == heap
    _assert_close(heap, expected_heap, deviation_criteria)


@pytest.mark.parametrize(
    ("application", "heatmap_config", "rss_heap_memory", "external_heap_memory", "heap_memory"),
    [
        pytest.param(
            "example_heatmap_capon",
            _EXAMPLE_CAPON_CONFIG,
            memory.heatmap_capon_rss_heap_memory,
            memory.heatmap_capon_external_heap_memory,
            memory.heatmap_capon_heap_memory,
            id="capon",
        ),
        pytest.param(
            "example_heatmap_conventional",
            _EXAMPLE_CONVENTIONAL_CONFIG,
            memory.heatmap_conventional_rss_heap_memory,
            memory.heatmap_conventional_external_heap_memory,
            memory.heatmap_conventional_heap_memory,
            id="conventional",
        ),
        pytest.param(
            "example_heatmap_coherent",
            _EXAMPLE_COHERENT_CONFIG,
            memory.heatmap_coherent_rss_heap_memory,
            memory.heatmap_coherent_external_heap_memory,
            memory.heatmap_coherent_heap_memory,
            id="coherent",
        ),
        pytest.param(
            "example_heatmap_robust_capon",
            _EXAMPLE_ROBUST_CAPON_CONFIG,
            memory.heatmap_robust_capon_rss_heap_memory,
            memory.heatmap_robust_capon_external_heap_memory,
            memory.heatmap_robust_capon_heap_memory,
            id="robust_capon",
        ),
    ],
)
def test_heatmap_memory_model(
    application: str,
    heatmap_config: HeatmapConfigCommon,
    rss_heap_memory: RssHeapMemoryFunction,
    external_heap_memory: HeapMemoryFunction,
    heap_memory: HeapMemoryFunction,
    xv211_memory_usage: dict[str, t.Any],
    deviation_criteria: float,
) -> None:
    expected_heap = xv211_memory_usage[application]["internal_aps"]["heap"]
    session_config = _example_session_config(sweeps_per_frame=1)

    rss_heap = rss_heap_memory(session_config)
    external_heap = external_heap_memory(session_config, heatmap_config)
    heap = heap_memory(session_config, heatmap_config)

    assert rss_heap + external_heap == heap
    _assert_close(heap, expected_heap, deviation_criteria)


@pytest.mark.parametrize(
    ("sweeps_per_frame", "heap_memory", "heatmap_config", "expected_heap"),
    [
        pytest.param(
            2,
            lambda session_config, _: memory.session_heap_memory(session_config),
            None,
            652,
            id="service_iq",
        ),
        pytest.param(
            1, memory.heatmap_capon_heap_memory, _EXAMPLE_CAPON_CONFIG, 40436, id="capon"
        ),
        pytest.param(
            1,
            memory.heatmap_conventional_heap_memory,
            _EXAMPLE_CONVENTIONAL_CONFIG,
            4168,
            id="conventional",
        ),
        pytest.param(
            1, memory.heatmap_coherent_heap_memory, _EXAMPLE_COHERENT_CONFIG, 6188, id="coherent"
        ),
        pytest.param(
            1,
            memory.heatmap_robust_capon_heap_memory,
            _EXAMPLE_ROBUST_CAPON_CONFIG,
            13952,
            id="robust_capon",
        ),
    ],
)
def test_heap_matches_sdk_example_allocations(
    sweeps_per_frame: int,
    heap_memory: HeapMemoryFunction,
    heatmap_config: t.Optional[HeatmapConfigCommon],
    expected_heap: int,
) -> None:
    """Traced from the Linux build of the SDK examples, less the 64-bit pointer slack"""
    assert heap_memory(_example_session_config(sweeps_per_frame), heatmap_config) == expected_heap


def test_movement_mode_adds_a_time_filter() -> None:
    session_config = _example_session_config(sweeps_per_frame=1)

    conventional_delta = memory.heatmap_conventional_external_heap_memory(
        session_config,
        attrs.evolve(
            _EXAMPLE_CONVENTIONAL_CONFIG,
            heatmap_mode=conventional.HeatmapConfig.HeatmapMode.MOVEMENT,
        ),
    ) - memory.heatmap_conventional_external_heap_memory(
        session_config, _EXAMPLE_CONVENTIONAL_CONFIG
    )
    coherent_delta = memory.heatmap_coherent_external_heap_memory(
        session_config,
        attrs.evolve(
            _EXAMPLE_COHERENT_CONFIG, heatmap_mode=coherent.HeatmapConfig.HeatmapMode.MOVEMENT
        ),
    ) - memory.heatmap_coherent_external_heap_memory(session_config, _EXAMPLE_COHERENT_CONFIG)

    assert conventional_delta == coherent_delta > 0


def test_frame_buffer_matches_rss_unit_test() -> None:
    """The RSS translation unit test expects a 1240 byte frame for this config"""
    session_config = _session_config(
        sweeps_per_frame=3,
        jitter_compensation=False,
        num_points=99,
        tx_antenna_mask=0b001,
        rx_antenna_mask=0b0001,
    )

    assert (
        memory.session_external_heap_memory(session_config)
        == 1240 + memory.MEASURE_RESULTS_CONTEXT_SIZE
    )


@pytest.mark.parametrize(("num_points", "packet_slack"), [(99, 16), (100, 64), (101, 48)])
def test_jitter_compensation_fills_packet_slack(num_points: int, packet_slack: int) -> None:
    """The loopback packet is added and the padding of the previously last subsweep is freed"""

    def session_config(jitter_compensation: bool) -> a2.SessionConfig:
        return _session_config(
            sweeps_per_frame=1,
            num_points=num_points,
            tx_antenna_mask=0b111,
            rx_antenna_mask=0b1111,
            jitter_compensation=jitter_compensation,
        )

    without = session_config(jitter_compensation=False)
    with_ = session_config(jitter_compensation=True)

    assert memory.session_rss_heap_memory(with_) == memory.session_rss_heap_memory(without)
    assert (
        memory.session_external_heap_memory(with_) - memory.session_external_heap_memory(without)
        == packet_slack
    )


def test_heatmap_model_takes_a_single_subsweep() -> None:
    """The Resource Calculator inputs and the Stream tab plugins enforce this"""
    session_config = a2.SessionConfig(
        [a2.SensorConfig.identical_subsweeps(num_subsweeps=2)], update_rate=None
    )

    with pytest.raises(AttributeError):
        memory.heatmap_capon_external_heap_memory(session_config, _EXAMPLE_CAPON_CONFIG)


@pytest.mark.parametrize(
    ("num_points", "expected_noise_points"),
    [(1, 100), (3, 100), (100, 100)],
)
def test_noise_measurement_resizes_to_the_wanted_sample_count(
    num_points: int, expected_noise_points: int
) -> None:
    """The noise buffer is sized for the resized config, not the configured one"""
    session_config = _session_config(num_points=num_points, sweeps_per_frame=1)
    sensor_config = session_config.sensor_config
    subsweep = sensor_config.subsweep

    buffer_size = memory._noise_normalization_buffer_size(
        sensor_config,
        sweeps_per_frame=1,
        n_wanted_samples=memory.NOISE_N_WANTED_SAMPLES,
        pool_noise_per_rx=False,
    )
    noise_estimates = subsweep.num_channels * (
        memory.SIZE_OF_COMPLEX_FLOAT + memory.SIZE_OF_FLOAT + memory.SIZE_OF_UINT32
    )

    assert buffer_size - noise_estimates == memory._radar_buffer_size(
        [expected_noise_points * subsweep.num_channels * memory.BYTES_PER_POINT],
        sweeps_per_frame=1,
        jitter_compensation=sensor_config.jitter_compensation,
    )


@pytest.mark.parametrize(
    ("num_points", "expect_clamped"),
    [(1, True), (6, True), (7, False), (1000, False)],
)
def test_small_configs_still_get_a_calibration_buffer(
    num_points: int, expect_clamped: bool
) -> None:
    """RSS asks for a buffer it can calibrate in, however small the frame is"""
    session_config = _session_config(num_points=num_points, sweeps_per_frame=1)

    external_heap = memory.session_external_heap_memory(session_config)

    assert (external_heap == memory.MIN_CALIBRATION_BUFFER_SIZE) == expect_clamped
    assert external_heap >= memory.MIN_CALIBRATION_BUFFER_SIZE


def test_session_memory_model_multiple_sensor_configs() -> None:
    """The radar buffer is shared between configs, the RSS structs are not"""
    small = a2.SensorConfig.single_subsweep(num_points=10)
    large = a2.SensorConfig.single_subsweep(num_points=1000)

    both = a2.SessionConfig([small, large], update_rate=None)
    large_only = a2.SessionConfig([large], update_rate=None)

    assert memory.session_rss_heap_memory(both) == 2 * memory.session_rss_heap_memory(large_only)
    assert memory.session_external_heap_memory(both) == memory.session_external_heap_memory(
        large_only
    )
