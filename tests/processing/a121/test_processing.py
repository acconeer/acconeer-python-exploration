# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import contextlib
import importlib.resources
import typing as t
from pathlib import Path

import h5py
import pytest

from acconeer.exptool import a121, opser
from acconeer.exptool.a121.algo import (
    touchless_button,
)

from . import (
    breathing_test,
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
def output_path_opser(input_path: Path, algorithm_factory: AlgorithmFactory) -> Path:
    """Returns the output path, that is based on the input path."""
    return input_path.with_name(f"{input_path.stem}-{algorithm_factory.__name__}-opser-output.h5")


@pytest.fixture
def input_path(resource_name: str) -> Path:
    """Returns the input path, given a resource name (in the "resources" package)"""
    with importlib.resources.path(resources, resource_name) as path:
        return path


@pytest.mark.parametrize(
    (
        "algorithm_factory",
        "serializer",
        "result_type",
        "comparator",
        "resource_name",
    ),
    [
        (
            presence_test.presence_default,
            presence_test.PresenceResultH5Serializer,
            t.List[presence_test.ProcessorResultSlice],
            presence_test.result_comparator,
            "input-frame_rate_10Hz-sweeps_per_frame_4.h5",
        ),
        (
            presence_test.presence_default,
            presence_test.PresenceResultH5Serializer,
            t.List[presence_test.ProcessorResultSlice],
            presence_test.result_comparator,
            "input-presence-default.h5",
        ),
        (
            presence_test.presence_short_range,
            presence_test.PresenceResultH5Serializer,
            t.List[presence_test.ProcessorResultSlice],
            presence_test.result_comparator,
            "input-presence-short_range.h5",
        ),
        (
            presence_test.presence_long_range,
            presence_test.PresenceResultH5Serializer,
            t.List[presence_test.ProcessorResultSlice],
            presence_test.result_comparator,
            "input-presence-long_range.h5",
        ),
        (
            presence_test.presence_medium_range_phase_boost_no_timeout,
            presence_test.PresenceResultH5Serializer,
            t.List[presence_test.ProcessorResultSlice],
            presence_test.result_comparator,
            "input-presence-medium_range_phase_boost_no_timeout.h5",
        ),
        (
            distance_test.distance_processor,
            distance_test.DistanceProcessorResultH5Serializer,
            t.List[distance_test.ResultSlice],
            distance_test.processor_result_comparator,
            "input.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            t.List[distance_test.ResultSlice],
            distance_test.detector_result_comparator,
            "input-distance-detector-5_to_10cm.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            t.List[distance_test.ResultSlice],
            distance_test.detector_result_comparator,
            "input-distance-detector-5_to_20cm.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            t.List[distance_test.ResultSlice],
            distance_test.detector_result_comparator,
            "input-distance-detector-200_to_400cm.h5",
        ),
        (
            distance_test.distance_detector,
            distance_test.DistanceDetectorResultH5Serializer,
            t.List[distance_test.ResultSlice],
            distance_test.detector_result_comparator,
            "input-distance-detector-5_to_200_cm_close_range_cancellation_disabled.h5",
        ),
        (
            smart_presence_test.smart_presence_controller,
            smart_presence_test.SmartPresenceResultH5Serializer,
            t.List[smart_presence_test.RefAppResultSlice],
            smart_presence_test.smart_presence_result_comparator,
            "smart_presence.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            tank_level_test.TankLevelResultH5Serializer,
            t.List[tank_level_test.RefAppResultSlice],
            tank_level_test.tank_level_result_comparator,
            "medium_tank.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            tank_level_test.TankLevelResultH5Serializer,
            t.List[tank_level_test.RefAppResultSlice],
            tank_level_test.tank_level_result_comparator,
            "small_tank.h5",
        ),
        (
            touchless_button_test.touchless_button_default,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            t.List[touchless_button.ProcessorResult],
            touchless_button_test.result_comparator,
            "input-touchless_button_default.h5",
        ),
        (
            touchless_button_test.touchless_button_both_ranges,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            t.List[touchless_button.ProcessorResult],
            touchless_button_test.result_comparator,
            "input-touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_patience,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            t.List[touchless_button.ProcessorResult],
            touchless_button_test.result_comparator,
            "input-touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_sensitivity,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            t.List[touchless_button.ProcessorResult],
            touchless_button_test.result_comparator,
            "input-touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_calibration,
            touchless_button_test.TouchlessButtonResultH5Serializer,
            t.List[touchless_button.ProcessorResult],
            touchless_button_test.result_comparator,
            "input-touchless_button_calibration.h5",
        ),
        (
            breathing_test.breathing_controller,
            breathing_test.BreathingResultH5Serializer,
            t.List[breathing_test.RefAppResultSlice],
            breathing_test.breathing_result_comparator,
            "breathing-sitting.h5",
        ),
        (
            breathing_test.breathing_controller,
            breathing_test.BreathingResultH5Serializer,
            t.List[breathing_test.RefAppResultSlice],
            breathing_test.breathing_result_comparator,
            "breathing-sitting-no-presence.h5",
        ),
    ],
)
def test_input_output(
    algorithm_factory: AlgorithmFactory,
    serializer: t.Type[H5ResultSerializer[t.List[AlgorithmResult]]],
    result_type: type,
    comparator: t.Callable[[AlgorithmResult, AlgorithmResult], bool],
    input_path: Path,
    output_path: Path,
    output_path_opser: Path,
    should_update_outputs: bool,  # from conftest.py
) -> None:
    with h5py.File(input_path) as f:
        r = a121.H5Record(f)
        algorithm = algorithm_factory(r)
        if hasattr(algorithm, "process"):
            actual_results = [algorithm.process(result) for result in r.results]
        elif hasattr(algorithm, "get_next"):
            actual_results = [
                algorithm.get_next()
                for idx in range(r.num_sessions)
                for _ in r.session(idx).extended_results
            ]
        else:
            raise AttributeError("Algorithm does not have process() or get_next()")

    if should_update_outputs:
        with contextlib.suppress(FileNotFoundError):
            output_path.unlink()

        with h5py.File(output_path, "w") as out:
            serializer(out.create_group("results")).serialize(actual_results)

    with h5py.File(output_path, "r") as out:
        expected_results = serializer(out.require_group("results")).deserialize(None)

    with h5py.File(output_path_opser, "w") as out:
        opser.serialize(actual_results, out, override_type=result_type)

    with h5py.File(output_path_opser, "r") as out:
        expected_results_opser: t.Any = opser.deserialize(out, result_type)

    assert len(expected_results) == len(actual_results) == len(expected_results_opser)

    for i, (expected_result, expected_result_opser, actual_result) in enumerate(
        zip(expected_results, expected_results_opser, actual_results)
    ):
        assert comparator(expected_result, actual_result), f"failed at {i}"
        assert comparator(expected_result, expected_result_opser), f"failed at {i}"
