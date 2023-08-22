# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import math
from typing import Dict, Optional

import pytest
import yaml

from acconeer.exptool.a121 import SensorConfig, SubsweepConfig
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
        rss_heap_mem = memory.service_rss_heap_memory(config)
        external_heap_mem = memory.service_external_heap_memory(config)
        heap_mem = memory.service_heap_memory(config)

        assert rss_heap_mem + external_heap_mem == heap_mem
        assert math.isclose(mem_usage["rss_heap"], rss_heap_mem, abs_tol=10)
        assert math.isclose(mem_usage["app_heap"], external_heap_mem, abs_tol=10)
