# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import importlib.resources
import typing as t
from pathlib import Path

import h5py
import pytest

from acconeer.exptool import a121

from . import (
    distance_test,
    presence_test,
    resources,
    smart_presence_test,
    tank_level_test,
    touchless_button_test,
)
from .misc import AlgorithmFactory, AlgorithmResult, H5ResultSerializer


@pytest.fixture
def output_path(input_path: Path, algorithm_factory: AlgorithmFactory) -> Path:
    """Returns the output path, that is based on the input path."""
    return input_path.with_name(f"{input_path.stem}-{algorithm_factory.__name__}-output.h5")


@pytest.fixture
def input_path(resource_name: str) -> Path:
    """Returns the input path, given a resource name (in the "resources" package)"""
    with importlib.resources.path(resources, resource_name) as path:
        return path


@pytest.mark.parametrize(
    (
        "algorithm_factory",
        "serializer",
        "comparator",
        "resource_name",
    ),
    [
        (
            presence_test.presence_default,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-frame_rate_10Hz-sweeps_per_frame_4.h5",
        ),
        (
            presence_test.presence_default,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-default.h5",
        ),
        (
            presence_test.presence_short_range,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-short_range.h5",
        ),
        (
            presence_test.presence_long_range,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-long_range.h5",
        ),
        (
            presence_test.presence_medium_range_phase_boost_no_timeout,
            presence_test.PresenceResultH5Serializer,
            presence_test.result_comparator,
            "input-presence-medium_range_phase_boost_no_timeout.h5",
        ),
        (
            distance_test.distance_processor,
            distance_test.DistanceProcessorResultH5Serializer,
            distance_test.processor_result_comparator,
            "input.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            distance_test.detector_result_comparator,
            "input-distance-detector-5_to_10cm.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            distance_test.detector_result_comparator,
            "input-distance-detector-5_to_20cm.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            distance_test.detector_result_comparator,
            "input-distance-detector-200_to_400cm.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            distance_test.detector_result_comparator,
            "input-distance-detector-5_to_200_cm_close_range_cancellation_disabled.h5",
        ),
        (
            smart_presence_test.smart_presence_controller,
            smart_presence_test.SmartPresenceResultH5Serializer,
            smart_presence_test.smart_presence_result_comparator,
            "smart_presence.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            tank_level_test.TankLevelResultH5Serializer,
            tank_level_test.tank_level_result_comparator,
            "medium_tank.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            tank_level_test.TankLevelResultH5Serializer,
            tank_level_test.tank_level_result_comparator,
            "small_tank.h5",
        ),
        (
            touchless_button_test.touchless_button_default,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            touchless_button_test.result_comparator,
            "input-touchless_button_default.h5",
        ),
        (
            touchless_button_test.touchless_button_both_ranges,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            touchless_button_test.result_comparator,
            "input-touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_patience,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            touchless_button_test.result_comparator,
            "input-touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_sensitivity,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            touchless_button_test.result_comparator,
            "input-touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_calibration,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            touchless_button_test.result_comparator,
            "input-touchless_button_calibration.h5",
        ),
    ],
)
def test_input_output(
    algorithm_factory: AlgorithmFactory,
    serializer: t.Type[H5ResultSerializer[t.List[AlgorithmResult]]],
    comparator: t.Callable[[AlgorithmResult, AlgorithmResult], bool],
    input_path: Path,
    output_path: Path,
    should_update_outputs: bool,  # from conftest.py
) -> None:
    with h5py.File(input_path) as f:
        r = a121.H5Record(f)
        algorithm = algorithm_factory(r)
        if hasattr(algorithm, "process"):
            actual_results = [algorithm.process(result) for result in r.results]
        elif hasattr(algorithm, "get_next"):
            actual_results = [algorithm.get_next() for _ in r.extended_results]
        else:
            raise AttributeError("Algorithm does not have process() or get_next()")

    if should_update_outputs:
        output_path.unlink(missing_ok=True)
        with h5py.File(output_path, "w") as out:
            serializer(out.create_group("results")).serialize(actual_results)

    with h5py.File(output_path, "r") as out:
        expected_algorithm_results = serializer(out.require_group("results")).deserialize(None)

    assert len(expected_algorithm_results) == len(actual_results)
    for expected_result, actual_result in zip(expected_algorithm_results, actual_results):
        assert comparator(expected_result, actual_result)
