# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import math
from typing import Dict, Optional

import pytest
import yaml

from acconeer.exptool.a121 import SensorConfig, SessionConfig, SubsweepConfig
from acconeer.exptool.a121.algo.distance import (
    DetectorConfig as DistanceConfig,
)
from acconeer.exptool.a121.algo.distance import (
    ThresholdMethod,
)
from acconeer.exptool.a121.algo.presence import _configs as PresenceConfigs
from acconeer.exptool.a121.model import memory


MEMORY_USAGE_YAML = "stash/python_libs/test_utils/memory_usage.yaml"


def memory_usage(application) -> Optional[Dict[str, int]]:
    try:
        with open(MEMORY_USAGE_YAML, encoding="utf-8") as yaml_file:
            mem_usage = yaml.safe_load(yaml_file)

        return mem_usage["devices"]["xm125"][application]

    except Exception:
        return None


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
def test_service_memory_model(config, application, test_case):
    mem_usage = memory_usage(application)
    test_case_key = test_case + "-internal_xm125"

    if mem_usage is None:
        pytest.skip("No memory reference")
    else:
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
def test_presence_memory_model(config, test_case):
    mem_usage = memory_usage("example_detector_presence")
    test_case_key = test_case + "-internal_xm125"

    if mem_usage is None:
        pytest.skip("No memory reference")
    else:
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
def test_distance_memory_model(config, test_case):
    mem_usage = memory_usage("example_detector_distance")
    test_case_key = test_case + "-internal_xm125"

    if mem_usage is None:
        pytest.skip("No memory reference")
    else:
        mem_usage = mem_usage[test_case_key]

        distance_rss_heap_mem = memory.distance_rss_heap_memory(config)
        distance_ext_heap_mem = memory.distance_external_heap_memory(config)
        distance_heap_mem = memory.distance_heap_memory(config)

        assert distance_rss_heap_mem + distance_ext_heap_mem == distance_heap_mem
        assert math.isclose(mem_usage["rss_heap"], distance_rss_heap_mem, rel_tol=0.05)
        assert math.isclose(mem_usage["app_heap"], distance_ext_heap_mem, rel_tol=0.05)
