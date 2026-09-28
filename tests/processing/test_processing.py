# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
from __future__ import annotations

import contextlib
import typing as t
from importlib.resources import as_file, files
from pathlib import Path

import h5py
import numpy as np
import numpy.typing as npt
import pytest
import typing_extensions as te

from acconeer.exptool import a2, a121, opser
from acconeer.exptool.a121._core_ext import ReplaySessionsExhaustedError, _StopReplay

from .a2 import data_files as data_files_a2
from .a2 import heatmap_test, motion_detection_test
from .a121 import (
    breathing_test,
    cargo_test,
    data_files,
    distance_test,
    hand_motion_test,
    parking_test,
    presence_test,
    smart_presence_test,
    surface_velocity_test,
    tank_level_test,
    touchless_button_test,
    vibration_test,
    waste_level_test,
)


AlgorithmFactory = t.Callable[[a121.H5Record], t.Any]


def get_output_path(input_path: Path, algorithm_name: str) -> Path:
    algo_parts_not_in_input_file = [
        part for part in algorithm_name.split("_") if part not in input_path.name
    ]
    if len(algo_parts_not_in_input_file) == 0:
        output_file_name = input_path.name
    else:
        output_file_name = f"{input_path.stem}-{'_'.join(algo_parts_not_in_input_file)}.h5"
    data_files_dir = input_path.parent / ".."

    return data_files_dir / "expected_output" / output_file_name


@pytest.fixture
def output_path(input_path: Path, algorithm_factory: AlgorithmFactory) -> Path:
    """Returns the output path, that is based on the input path."""
    return get_output_path(input_path, algorithm_factory.__name__)


@pytest.fixture
def input_path(resource_name: str) -> Path:
    """Returns the input path, given a resource name (in the "data_files" package)"""
    with as_file(files(data_files.recorded_data) / resource_name) as path:
        return path


@pytest.mark.parametrize(
    (
        "algorithm_factory",
        "result_type",
        "resource_name",
    ),
    [
        (
            parking_test.parking_default,
            list[parking_test.ResultSlice],
            "parking_ground_default.h5",
        ),
        (
            parking_test.parking_default,
            list[parking_test.ResultSlice],
            "parking_pole.h5",
        ),
        (
            presence_test.presence_default,
            list[presence_test.ProcessorResultSlice],
            "fr10Hz-spf4.h5",
        ),
        (
            presence_test.presence_default,
            list[presence_test.ProcessorResultSlice],
            "presence-default.h5",
        ),
        (
            presence_test.presence_short_range,
            list[presence_test.ProcessorResultSlice],
            "presence-short_range.h5",
        ),
        (
            presence_test.presence_long_range,
            list[presence_test.ProcessorResultSlice],
            "presence-long_range.h5",
        ),
        (
            presence_test.presence_low_power,
            list[presence_test.ProcessorResultSlice],
            "presence-low_power.h5",
        ),
        (
            presence_test.presence_medium_range_no_timeout,
            list[presence_test.ProcessorResultSlice],
            "presence-medium_range_no_timeout.h5",
        ),
        (
            distance_test.distance_processor,
            list[distance_test.ResultSlice],
            "input.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-5to10.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-5to20.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-200to400.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-5to200_no_cr_cancel.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-5to200_p1_no_cr_cancel.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "corner-reflector.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance_fixed_strength.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-multi-group.h5",
        ),
        (
            distance_test.distance_detector,
            list[distance_test.ResultSlice],
            "distance-multi-group-close-range-enabled.h5",
        ),
        (
            smart_presence_test.smart_presence_controller,
            list[smart_presence_test.RefAppResultSlice],
            "smart_presence.h5",
        ),
        (
            smart_presence_test.smart_presence_controller,
            list[smart_presence_test.RefAppResultSlice],
            "smart_presence-low_power.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            list[tank_level_test.RefAppResultSlice],
            "medium_tank.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            list[tank_level_test.RefAppResultSlice],
            "small_tank.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            list[tank_level_test.RefAppResultSlice],
            "large_tank.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            list[tank_level_test.RefAppResultSlice],
            "medium_tank_level_track.h5",
        ),
        (
            tank_level_test.tank_level_controller,
            list[tank_level_test.RefAppResultSlice],
            "large_tank_level_track.h5",
        ),
        (
            touchless_button_test.touchless_button_processor,
            list[touchless_button_test.ResultSlice],
            "touchless_button_default.h5",
        ),
        (
            touchless_button_test.touchless_button_processor,
            list[touchless_button_test.ResultSlice],
            "touchless_button_both_ranges.h5",
        ),
        (
            touchless_button_test.touchless_button_processor,
            list[touchless_button_test.ResultSlice],
            "touchless_button_patience.h5",
        ),
        (
            touchless_button_test.touchless_button_processor,
            list[touchless_button_test.ResultSlice],
            "touchless_button_sensitivity.h5",
        ),
        (
            touchless_button_test.touchless_button_processor,
            list[touchless_button_test.ResultSlice],
            "touchless_button_calibration.h5",
        ),
        (
            breathing_test.breathing_controller,
            list[breathing_test.RefAppResultSlice],
            "breathing-sitting.h5",
        ),
        (
            breathing_test.breathing_controller,
            list[breathing_test.RefAppResultSlice],
            "breathing-sitting-no-presence.h5",
        ),
        (
            surface_velocity_test.surface_velocity_controller,
            list[surface_velocity_test.ResultSlice],
            "surface_velocity_1_dist.h5",
        ),
        (
            surface_velocity_test.surface_velocity_controller,
            list[surface_velocity_test.ResultSlice],
            "surface_velocity_4_dist.h5",
        ),
        (
            surface_velocity_test.surface_velocity_controller,
            list[surface_velocity_test.ResultSlice],
            "surface_velocity_default.h5",
        ),
        (
            vibration_test.vibration_controller,
            list[vibration_test.ResultSlice],
            "vibration_low_frequency.h5",
        ),
        (
            vibration_test.vibration_controller,
            list[vibration_test.ResultSlice],
            "vibration.h5",
        ),
        (
            waste_level_test.waste_level_processor,
            list[waste_level_test.ResultSlice],
            "waste-level-empty.h5",
        ),
        (
            waste_level_test.waste_level_processor,
            list[waste_level_test.ResultSlice],
            "waste-level-25-percent.h5",
        ),
        (
            waste_level_test.waste_level_processor,
            list[waste_level_test.ResultSlice],
            "waste-level-75-percent.h5",
        ),
        (
            waste_level_test.waste_level_processor,
            list[waste_level_test.ResultSlice],
            "waste-level-full.h5",
        ),
        (
            waste_level_test.waste_level_processor,
            list[waste_level_test.ResultSlice],
            "waste-level-missing-level.h5",
        ),
        (
            hand_motion_test.hand_motion_app,
            list[hand_motion_test.ResultSlice],
            "hand-motion-default.h5",
        ),
        (
            hand_motion_test.hand_motion_app,
            list[hand_motion_test.ResultSlice],
            "hand-motion-no-presence.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_10_feet.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_10_feet_only_presence.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_10_feet_only_presence_2.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_20_feet.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_20_feet_no_lens.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_20_feet_no_lens_add_presence.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_20_feet_utilization_and_presence.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_20_feet_utilization_and_presence_2.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_40_feet.h5",
        ),
        (
            cargo_test.cargo_app,
            list[cargo_test.ResultSlice],
            "cargo_util_and_pres_steering_distance.h5",
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
            actual_results = []
            try:
                while True:
                    result = algorithm.get_next()
                    actual_results.append(result)
            except (
                _StopReplay,
                ReplaySessionsExhaustedError,
            ):  # record file exhausted. Stop replay.
                pass
        else:
            msg = "Algorithm does not have process() or get_next()"
            raise AttributeError(msg)

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


@pytest.mark.parametrize(
    ("resource_name", "processor_factory"),
    [
        ("capon_heatmap.h5", heatmap_test.capon_heatmap_processing),
        ("coherent_heatmap.h5", heatmap_test.coherent_heatmap_processing),
        ("conventional_heatmap.h5", heatmap_test.conventional_heatmap_processing),
        ("conventional_heatmap_movement.h5", heatmap_test.conventional_heatmap_processing),
    ],
)
def test_heatmap_processor(
    resource_name: str,
    processor_factory: t.Callable[[a2.H5Record], tuple[t.Any, t.Any]],
    should_update_outputs: bool,
) -> None:
    with (
        as_file(files(data_files_a2.recorded_data) / resource_name) as input_path,
        a2.open_record(input_path) as record,
    ):
        processor, noise_normalization_processor, _ = processor_factory(record)
        heatmaps = []
        heatmaps_type: te.TypeAlias = list[npt.NDArray[np.float64]]

        for idx, result in enumerate(record.results):
            group_result = noise_normalization_processor.process(result)
            result = processor.process(group_result)
            if result.heatmap is None:
                continue
            heatmaps.append(result.heatmap)
        output_path = get_output_path(input_path, "heatmap")
        if should_update_outputs:
            with contextlib.suppress(FileNotFoundError):
                output_path.unlink()
            with h5py.File(output_path, "w") as expected_out:
                opser.serialize(heatmaps, expected_out, override_type=heatmaps_type)
        with h5py.File(output_path, "r") as expected_out:
            expected_results = opser.deserialize(expected_out, heatmaps_type)
            # Check that we have at least one non-NaN in the data
            assert not np.all(np.isnan(expected_results))

        assert len(expected_results) == len(heatmaps)
        for expected, actual in zip(expected_results, heatmaps):
            np.testing.assert_allclose(expected, actual, atol=1e-7)


@pytest.mark.parametrize(
    ("resource_name", "processor_factory"),
    [
        (
            "motion_detection_processor.h5",
            motion_detection_test.motion_detection_default,
        ),
    ],
)
def test_motion_detection_processor(
    resource_name: str,
    processor_factory: t.Callable[
        [a2.H5Record], "a2.algo.motion_detection.MotionDetectionProcessor"
    ],
    should_update_outputs: bool,
) -> None:
    with (
        as_file(files(data_files_a2.recorded_data) / resource_name) as input_path,
        a2.open_record(input_path) as record,
    ):
        processor = processor_factory(record)

        # Skip the first few frames: while the Capon covariance matrix warms up
        # it is near-singular, so its matrix inversion amplifies float-rounding
        # differences enough to diverge across numpy/BLAS/CPU environments.
        # Steady-state frames are the only reproducible target.
        warmup = 4

        HeatmapType: te.TypeAlias = npt.NDArray[np.float64]
        ThresholdMapType: te.TypeAlias = npt.NDArray[np.float64]
        DetectionsType: te.TypeAlias = list[tuple[float, float, float]]
        MotionDetectionResultsType: te.TypeAlias = list[
            tuple[HeatmapType, ThresholdMapType, DetectionsType]
        ]

        actual: MotionDetectionResultsType = []
        for result in record.results:
            md_result = processor.process(result)
            detections: DetectionsType = [
                (
                    float(p.spherical_position[1]),
                    float(p.spherical_position[0]),
                    float(p.amplitude),
                )
                for p in md_result.peaks
            ]
            actual.append((md_result.heatmap, md_result.threshold_map, detections))

        output_path = get_output_path(input_path, "motion_detection_processor")
        if should_update_outputs:
            with contextlib.suppress(FileNotFoundError):
                output_path.unlink()
            with h5py.File(output_path, "w") as expected_out:
                opser.serialize(actual, expected_out, override_type=MotionDetectionResultsType)
        with h5py.File(output_path, "r") as expected_out:
            expected = opser.deserialize(expected_out, MotionDetectionResultsType)

        assert len(expected) == len(actual)

        for (e_h, _, _), (a_h, _, _) in zip(expected[warmup:], actual[warmup:]):
            np.testing.assert_allclose(e_h, a_h, atol=1e-7)
        for (_, e_t, _), (_, a_t, _) in zip(expected[warmup:], actual[warmup:]):
            np.testing.assert_allclose(e_t, a_t, atol=1e-7)
        for (_, _, e_d), (_, _, a_d) in zip(expected[warmup:], actual[warmup:]):
            np.testing.assert_allclose(np.array(e_d), np.array(a_d), atol=1e-7)


def test_ap212_angle_prevalency() -> None:
    """This file is a recording of a corner reflector using the ap212.

    The corner reflector is offset in both angles and has a distance of ~50cm from the sensor.
    (distance is not important for this test though).

    To describe the reflector position; imagine looking straight at the sensor, separating
    the space between you and the sensor into 4 quadrants by

    - one horizontal plane, intersecting with both your eyes and dividing the sensor chip along its long side [1]
    - one vertical plane, dividing your nose into 2 symmetrical parts and dividing the sensor chip along its short side [2]

    Then the position of the corner reflector is in the quite far up in the lower left quadrant.

                |
                |
                |
            +-------+
     -------| ##### |------- [1]
       .<   +-------+
       |        |
                |
                |
               [2]
    """
    input_file = "angle_prevalency.h5"

    with (
        as_file(files(data_files_a2.recorded_data) / input_file) as input_path,
        a2.open_record(input_path) as record,
    ):
        processor, _ = heatmap_test.heatmap_from_record(record)

        ap212_heatmaps = []
        for idx, result in enumerate(record.results):
            print(idx)
            result = processor.process(result)
            if result.heatmap is None or idx < 12:
                continue
            ap212_heatmaps.append(
                result.heatmap
            )  # The heatmap is a 3d object with 23 az angles and 53 el angles.

        max_depth_time = np.max(ap212_heatmaps, axis=(0, 1))  # Take max over depths and time.

        max_az_ind = np.argmax(np.max(max_depth_time, axis=1))
        max_el_ind = np.argmax(np.max(max_depth_time, axis=0))

        max_az_angle = processor.heatmap_config.az_angles[max_az_ind]
        max_el_angle = processor.heatmap_config.el_angles[max_el_ind]

        assert np.isclose(max_az_angle, 30.0, atol=10.1)
        assert np.isclose(max_el_angle, -5.0, atol=10.1)
