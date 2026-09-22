# Copyright (c) Acconeer AB, 2026
# All rights reserved

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import DetectorConfig, ThresholdMethod
from acconeer.exptool.a121.model import memory


@pytest.mark.parametrize(
    "config",
    [
        pytest.param(
            DetectorConfig(
                start_m=0.038,
                end_m=0.043,
                max_step_length=1,
                max_profile=a121.Profile.PROFILE_1,
                close_range_leakage_cancellation=False,
                signal_quality=-10.0,
                threshold_method=ThresholdMethod.CFAR,
            ),
            id="short-range-in-direct-leakage",
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.5,
                end_m=0.52,
                max_step_length=24,
                max_profile=a121.Profile.PROFILE_5,
                threshold_method=ThresholdMethod.FIXED,
            ),
            id="short-range-coarse-step",
        ),
        pytest.param(
            DetectorConfig(
                start_m=0.05,
                end_m=0.2,
                close_range_leakage_cancellation=True,
                threshold_method=ThresholdMethod.FIXED_STRENGTH,
            ),
            id="close-range",
        ),
    ],
)
def test_distance_heap_memory_handles_ranges_with_collapsed_subsweeps(
    config: DetectorConfig,
) -> None:
    """A range too short to fill every subsweep must still be modelled."""

    rss_heap = memory.distance_rss_heap_memory(config)
    external_heap = memory.distance_external_heap_memory(config)

    assert memory.distance_heap_memory(config) == rss_heap + external_heap
