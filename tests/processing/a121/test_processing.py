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

from . import (
    data_files,
    surface_velocity_test,
)


AlgorithmFactory = t.Callable[[a121.H5Record], t.Any]


@pytest.fixture
def output_path(input_path: Path, algorithm_factory: AlgorithmFactory) -> Path:
    """Returns the output path, that is based on the input path."""
    output_file_name = f"{input_path.stem}-{algorithm_factory.__name__}-output.h5"
    data_files_dir = input_path.parent / ".."

    return data_files_dir / "expected_output" / output_file_name


@pytest.fixture
def input_path(resource_name: str) -> Path:
    """Returns the input path, given a resource name (in the "data_files" package)"""
    with importlib.resources.path(data_files.recorded_data, resource_name) as path:
        return path


@pytest.mark.parametrize(
    (
        "algorithm_factory",
        "result_type",
        "resource_name",
    ),
    [
        ##(
        ##presence_test.presence_default,
        ##t.List[presence_test.ProcessorResultSlice],
        ##"input-frame_rate_10Hz-sweeps_per_frame_4.h5",
        ##),
        ##(
        ##presence_test.presence_default,
        ##t.List[presence_test.ProcessorResultSlice],
        ##"input-presence-default.h5",
        ##),
        ##(
        ##presence_test.presence_short_range,
        ##t.List[presence_test.ProcessorResultSlice],
        ##"input-presence-short_range.h5",
        ##),
        ##(
        ##presence_test.presence_long_range,
        ##t.List[presence_test.ProcessorResultSlice],
        ##"input-presence-long_range.h5",
        ##),
        ##(
        ##presence_test.presence_medium_range_phase_boost_no_timeout,
        ##t.List[presence_test.ProcessorResultSlice],
        ##"input-presence-medium_range_phase_boost_no_timeout.h5",
        ##),
        ##(
        ##distance_test.distance_processor,
        ##t.List[distance_test.ResultSlice],
        ##"input.h5",
        ##),
        ##(
        ##distance_test.distance_detector,
        ##t.List[distance_test.ResultSlice],
        ##"input-distance-detector-5_to_10cm.h5",
        ##),
        ##(
        ##distance_test.distance_detector,
        ##t.List[distance_test.ResultSlice],
        ##"input-distance-detector-5_to_20cm.h5",
        ##),
        ##(
        ##distance_test.distance_detector,
        ##t.List[distance_test.ResultSlice],
        ##"input-distance-detector-200_to_400cm.h5",
        ##),
        ##(
        ##distance_test.distance_detector,
        ##t.List[distance_test.ResultSlice],
        ##"input-distance-detector-5_to_200_cm_close_range_cancellation_disabled.h5",
        ##),
        ##(
        ##distance_test.distance_detector,
        ##t.List[distance_test.ResultSlice],
        ##"corner-reflector.h5",
        ##),
        ##(
        ##distance_test.distance_detector,
        ##t.List[distance_test.ResultSlice],
        ##"distance_fixed_strength.h5",
        ##),
        ##(
        ##smart_presence_test.smart_presence_controller,
        ##t.List[smart_presence_test.RefAppResultSlice],
        ##"smart_presence.h5",
        ##),
        ##(
        ##tank_level_test.tank_level_controller,
        ##t.List[tank_level_test.RefAppResultSlice],
        ##"medium_tank.h5",
        ##),
        ##(
        ##tank_level_test.tank_level_controller,
        ##t.List[tank_level_test.RefAppResultSlice],
        ##"small_tank.h5",
        ##),
        ##(
        ##touchless_button_test.touchless_button_default,
        ##t.List[touchless_button_test.ResultSlice],
        ##"input-touchless_button_default.h5",
        ##),
        ##(
        ##touchless_button_test.touchless_button_both_ranges,
        ##t.List[touchless_button_test.ResultSlice],
        ##"input-touchless_button_both_ranges.h5",
        ##),
        ##(
        ##touchless_button_test.touchless_button_patience,
        ##t.List[touchless_button_test.ResultSlice],
        ##"input-touchless_button_both_ranges.h5",
        ##),
        ##(
        ##touchless_button_test.touchless_button_sensitivity,
        ##t.List[touchless_button_test.ResultSlice],
        ##"input-touchless_button_both_ranges.h5",
        ##),
        ##(
        ##touchless_button_test.touchless_button_calibration,
        ##t.List[touchless_button_test.ResultSlice],
        ##"input-touchless_button_calibration.h5",
        ##),
        ##(
        ##breathing_test.breathing_controller,
        ##t.List[breathing_test.RefAppResultSlice],
        ##"breathing-sitting.h5",
        ##),
        ##(
        ##breathing_test.breathing_controller,
        ##t.List[breathing_test.RefAppResultSlice],
        ##"breathing-sitting-no-presence.h5",
        ##),
        (
            surface_velocity_test.surface_velocity_controller,
            t.List[surface_velocity_test.ResultSlice],
            "input_surface_velocity_1_dist.h5",
        ),
        (
            surface_velocity_test.surface_velocity_controller,
            t.List[surface_velocity_test.ResultSlice],
            "input_surface_velocity_4_dist.h5",
        ),
        (
            surface_velocity_test.surface_velocity_controller,
            t.List[surface_velocity_test.ResultSlice],
            "input_surface_velocity_default.h5",
        ),
    ],
)
def test_input_output(
    algorithm_factory: AlgorithmFactory,
    result_type: type,
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
            opser.serialize(actual_results, out, override_type=result_type)

    with h5py.File(output_path, "r") as out:
        expected_results: t.Any = opser.deserialize(out, result_type)

    assert len(expected_results) == len(actual_results)

    for i, (expected_result, actual_result) in enumerate(zip(expected_results, actual_results)):
        assert expected_result == actual_result, f"failed at {i}"
