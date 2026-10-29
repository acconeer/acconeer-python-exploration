# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict
from unittest import mock

import pytest
import yaml

from acconeer.exptool.a121 import Profile, SensorConfig, SessionConfig, SubsweepConfig
from acconeer.exptool.a121.algo import APPROX_BASE_STEP_LENGTH_M, distance
from acconeer.exptool.a121.algo.distance import (
    Detector as DistanceDetector,
)
from acconeer.exptool.a121.algo.distance import (
    DetectorConfig as DistanceConfig,
)
from acconeer.exptool.a121.algo.distance import (
    ThresholdMethod,
)
from acconeer.exptool.a121.algo.distance._translation import get_num_far_subsweeps
from acconeer.exptool.a121.algo.presence import _configs as PresenceConfigs
from acconeer.exptool.a121.model import memory


@pytest.fixture
def xm125_memory_usage(memory_usage_path: Path) -> Dict[str, int]:
    with open(memory_usage_path, encoding="utf-8") as yaml_file:
        mem_usage = yaml.safe_load(yaml_file)
        return mem_usage["devices"]["xm125"]


@pytest.mark.parametrize(
    "config,application,test_case",
    [
        pytest.param(
            SensorConfig(start_point=80, num_points=160),
            "example_service",
            "default",
        ),
        pytest.param(
            SensorConfig(start_point=80, num_points=1990),
            "example_service",
            "long-range",
        ),
        pytest.param(
            SensorConfig(
                sweeps_per_frame=16,
                subsweeps=[
                    SubsweepConfig(
                        start_point=100,
                        num_points=5,
                    ),
                    SubsweepConfig(
                        start_point=300,
                        num_points=20,
                    ),
                    SubsweepConfig(
                        start_point=500,
                        num_points=10,
                    ),
                ],
            ),
            "example_service_subsweeps",
            "default",
        ),
    ],
)
def test_service_memory_model(config, application, test_case, xm125_memory_usage):
    mem_usage = xm125_memory_usage[application]
    test_case_key = test_case + "-internal_xm125"

    mem_usage = mem_usage[test_case_key]

    session_config = SessionConfig(config)
    session_rss_heap_mem = memory.session_rss_heap_memory(session_config)
    session_external_heap_mem = memory.session_external_heap_memory(session_config)
    session_heap_mem = memory.session_heap_memory(session_config)

    assert session_rss_heap_mem + session_external_heap_mem == session_heap_mem
    assert math.isclose(mem_usage["rss_heap"], session_rss_heap_mem, rel_tol=0.05)
    assert math.isclose(mem_usage["app_heap"], session_external_heap_mem, rel_tol=0.05)


@pytest.mark.parametrize(
    "config,test_case",
    [
        pytest.param(
            PresenceConfigs.get_short_range_config(),
            "short_range",
        ),
        pytest.param(
            PresenceConfigs.get_medium_range_config(),
            "default",
        ),
        pytest.param(
            PresenceConfigs.get_long_range_config(),
            "long_range",
        ),
    ],
)
def test_presence_memory_model(config, test_case, xm125_memory_usage):
    mem_usage = xm125_memory_usage["example_detector_presence"]
    test_case_key = test_case + "-internal_xm125"

    mem_usage = mem_usage[test_case_key]

    presence_rss_heap_mem = memory.presence_rss_heap_memory(config)
    presence_ext_heap_mem = memory.presence_external_heap_memory(config)
    presence_heap_mem = memory.presence_heap_memory(config)

    assert presence_rss_heap_mem + presence_ext_heap_mem == presence_heap_mem
    assert math.isclose(mem_usage["rss_heap"], presence_rss_heap_mem, rel_tol=0.05)
    assert math.isclose(mem_usage["app_heap"], presence_ext_heap_mem, rel_tol=0.05)


@pytest.mark.parametrize(
    "config,test_case",
    [
        pytest.param(
            DistanceConfig(
                start_m=0.1,
                end_m=3.0,
                threshold_method=ThresholdMethod.CFAR,
            ),
            "default",
        ),
        pytest.param(
            DistanceConfig(
                start_m=0.05,
                end_m=0.2,
                threshold_method=ThresholdMethod.RECORDED,
            ),
            "close_range",
        ),
        pytest.param(
            DistanceConfig(start_m=2.0, end_m=4.0, threshold_method=ThresholdMethod.CFAR),
            "long_range",
        ),
    ],
)
def test_distance_memory_model(config, test_case, xm125_memory_usage):
    mem_usage = xm125_memory_usage["example_detector_distance"]
    test_case_key = test_case + "-internal_xm125"

    mem_usage = mem_usage[test_case_key]

    distance_rss_heap_mem = memory.distance_rss_heap_memory(config)
    distance_ext_heap_mem = memory.distance_external_heap_memory(config)
    distance_heap_mem = memory.distance_heap_memory(config)

    assert distance_rss_heap_mem + distance_ext_heap_mem == distance_heap_mem
    assert math.isclose(mem_usage["rss_heap"], distance_rss_heap_mem, rel_tol=0.05)
    assert math.isclose(mem_usage["app_heap"], distance_ext_heap_mem, rel_tol=0.05)


# Ranges spanning a single base step make the max-profile breakpoints collapse,
# so the session config holds fewer than four far subsweeps.
_DEDUPLICATED_BREAKPOINT_CONFIGS = [
    pytest.param(
        DistanceConfig(
            start_m=1.0,
            end_m=1.0 + APPROX_BASE_STEP_LENGTH_M,
            max_profile=Profile.PROFILE_1,
            max_step_length=1,
            threshold_method=ThresholdMethod.CFAR,
        ),
        id="far-cfar-dedup",
    ),
    pytest.param(
        DistanceConfig(
            start_m=1.0,
            end_m=1.0 + APPROX_BASE_STEP_LENGTH_M,
            max_profile=Profile.PROFILE_1,
            max_step_length=1,
            threshold_method=ThresholdMethod.RECORDED,
        ),
        id="far-recorded-dedup",
    ),
    pytest.param(
        DistanceConfig(
            start_m=0.05,
            end_m=0.12 + APPROX_BASE_STEP_LENGTH_M,
            max_profile=Profile.PROFILE_1,
            max_step_length=1,
            close_range_leakage_cancellation=True,
            threshold_method=ThresholdMethod.RECORDED,
        ),
        id="close-far-recorded-dedup",
    ),
]

_OTHER_DISTANCE_CONFIGS = [
    pytest.param(
        DistanceConfig(start_m=0.1, end_m=3.0, threshold_method=ThresholdMethod.CFAR),
        id="far-cfar-multisubsweep",
    ),
    pytest.param(
        DistanceConfig(start_m=0.05, end_m=0.2, threshold_method=ThresholdMethod.RECORDED),
        id="far-recorded-transition",
    ),
    pytest.param(
        DistanceConfig(
            start_m=0.05,
            end_m=0.1,
            close_range_leakage_cancellation=True,
            threshold_method=ThresholdMethod.RECORDED,
        ),
        id="close-only-recorded",
    ),
]


def _detector_session_config_and_specs(config):
    # Bypass __init__ (which requires a client) and reuse the Detector's own composition.
    detector = DistanceDetector.__new__(DistanceDetector)
    detector.sensor_ids = [1]
    detector.update_config(config)
    return detector.session_config, detector.processor_specs


@pytest.mark.parametrize("config", _DEDUPLICATED_BREAKPOINT_CONFIGS)
def test_distance_dedup_configs_have_fewer_far_subsweeps(config):
    config.validate()
    session_config, _ = _detector_session_config_and_specs(config)

    num_far_subsweeps = get_num_far_subsweeps(session_config, config)

    assert 0 < num_far_subsweeps < 4


@pytest.mark.parametrize("config", _DEDUPLICATED_BREAKPOINT_CONFIGS + _OTHER_DISTANCE_CONFIGS)
def test_distance_memory_model_uses_detector_processor_specs(config):
    config.validate()
    session_config, detector_specs = _detector_session_config_and_specs(config)

    for spec in detector_specs:
        for ss_ref in spec.subsweep_references or []:
            sensor_config = session_config.groups[ss_ref.group_index][1]
            assert ss_ref.subsweep_index < sensor_config.num_subsweeps

    to_processor_specs = distance.detector_config_to_processor_specs
    with mock.patch.object(
        distance, "detector_config_to_processor_specs", wraps=to_processor_specs
    ) as spy:
        distance_rss_heap_mem = memory.distance_rss_heap_memory(config)
        distance_ext_heap_mem = memory.distance_external_heap_memory(config)

    assert spy.call_count == 2
    for call in spy.call_args_list:
        assert to_processor_specs(*call.args, **call.kwargs) == detector_specs
    assert distance_rss_heap_mem + distance_ext_heap_mem == memory.distance_heap_memory(config)
