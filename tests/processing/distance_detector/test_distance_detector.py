import tempfile
from contextlib import nullcontext as does_not_raise
from enum import Enum
from pathlib import Path

import h5py
import numpy as np
import pytest

import acconeer.exptool as et
from acconeer.exptool.a111.algo.distance_detector._processor import (
    ProcessingConfiguration,
    Processor,
)
from acconeer.exptool.a111.algo.distance_detector.calibration import DistanceDetectorCalibration


HERE = Path(__file__).parent

TEST_KEYS = [
    "threshold",
    "above_thres_hist_dist",
    "found_peaks",
]
PARAMETER_SETS = [
    {
        "threshold_type": ProcessingConfiguration.ThresholdType.CFAR,
        "cfar_sensitivity": 0.7,  # input produces no detections for default (=0.5)
    },
]
PARAMETER_SETS_CALIBRATION = [
    {"threshold_type": ProcessingConfiguration.ThresholdType.RECORDED},
]


def list_of_lists_to_matrix(list_of_lists):
    """
    Some of the parameters returns list of lists (with dynamic length). In
    order for these to be saved to a h5 file, they are put in a matrix with
    "nan-terminated" rows.
    """
    rows = len(list_of_lists)
    columns = max(len(list) for list in list_of_lists)
    matrix = np.full((rows, columns), fill_value=np.nan)

    for i, list in enumerate(list_of_lists):
        matrix[i, 0 : len(list)] = list

    return matrix


def get_output(parameter_set=None, processor_modifier=None):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()

    if parameter_set is not None:
        for k, v in parameter_set.items():
            setattr(processing_config, k, v)

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
    )

    if processor_modifier:
        processor = processor_modifier(processor)

    output = {k: [] for k in TEST_KEYS}

    for data_info, data in input_record:
        result = processor.process(data.squeeze(0), data_info[0])

        for k in TEST_KEYS:
            if result[k] is None:
                output[k].append([])
            else:
                output[k].append(result[k])

    return {key: list_of_lists_to_matrix(data) for key, data in output.items()}


def get_output_precalibrated(parameter_set=None):
    if parameter_set.get("threshold_type") != ProcessingConfiguration.ThresholdType.RECORDED:
        pytest.skip(f'Test is N/A with threshold_type={parameter_set.get("threshold_type")}')

    def calibration_updater(processor):
        calibration = DistanceDetectorCalibration.load(HERE / "calibration.npy")
        processor.update_calibration(calibration)
        return processor

    return get_output(parameter_set=parameter_set, processor_modifier=calibration_updater)


def get_calibration(parameter_set=None):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()

    if parameter_set is not None:
        for k, v in parameter_set.items():
            setattr(processing_config, k, v)

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
    )

    for data_info, data in input_record:
        output = processor.process(data.squeeze(0), data_info[0])
        if "new_calibration" in output:
            return output["new_calibration"]
    assert False


def save_output(file, output):
    with h5py.File(file, "w") as f:
        for k in TEST_KEYS:
            try:
                f.create_dataset(name=k, data=output[k], track_times=False)
            except TypeError as te:
                raise TypeError(f'Key "{k}" is probably of wrong type ({type(output[k])})') from te


def load_output(file):
    output = {}

    with h5py.File(file, "r") as f:
        for k in TEST_KEYS:
            output[k] = f[k][()]

    return output


def compare_output(expected, actual, exact=False):
    for k in TEST_KEYS:
        expected_arr = expected[k]
        actual_arr = actual[k]

        if exact:
            np.testing.assert_array_equal(expected_arr, actual_arr)
        else:
            np.testing.assert_allclose(expected_arr, actual_arr)


def path_for_parameter_set(parameter_set, calibration=False):
    if parameter_set:
        l = sorted(parameter_set.items())

        for i, (key, maybe_enum) in enumerate(l):
            if isinstance(maybe_enum, Enum):
                enum_member = maybe_enum
                l[i] = (key, enum_member.name.lower())

        suffix = "_".join(f"{k}-{v}" for k, v in l)
    else:
        suffix = "default"

    if calibration:
        suffix += "_calibration"

    return HERE / f"output_{suffix}.h5"


def test_load_save_compare():
    temp_file = tempfile.TemporaryFile()

    saved_output = get_output()

    save_output(temp_file, saved_output)
    loaded_output = load_output(temp_file)

    compare_output(saved_output, loaded_output, exact=True)


def test_path_for_parameter_set():
    class Test(Enum):
        MEMBER = 1

    assert path_for_parameter_set({"foo": "bar"}) == (HERE / "output_foo-bar.h5")
    assert path_for_parameter_set({"enum": Test.MEMBER}) == (HERE / "output_enum-member.h5")


def test_processor_against_reference():
    for parameter_set in PARAMETER_SETS:
        with open(path_for_parameter_set(parameter_set), "rb") as f:
            expected = load_output(f)

        actual = get_output(parameter_set)
        compare_output(expected, actual)


def test_processor_against_reference_calibrated():
    for parameter_set in PARAMETER_SETS_CALIBRATION:
        with open(path_for_parameter_set(parameter_set, calibration=True), "rb") as f:
            expected = load_output(f)

        actual = get_output_precalibrated(parameter_set)
        compare_output(expected, actual)


def test_calibration_against_reference_calibration():
    for parameter_set in PARAMETER_SETS_CALIBRATION:
        expected = np.load(HERE / "calibration.npy")
        actual = get_calibration(parameter_set)
        actual_legacy_format = np.array(
            [
                actual.stationary_clutter_mean,
                actual.stationary_clutter_std,
            ]
        )
        np.testing.assert_array_equal(expected, actual_legacy_format)


@pytest.mark.parametrize("reference_file", HERE.glob("output_*.h5"))
def test_output_references_have_detections(reference_file):
    reference = load_output(reference_file)

    found_peaks = reference.get("found_peaks")
    assert isinstance(found_peaks, np.ndarray)
    assert not np.isnan(found_peaks).all()


@pytest.mark.parametrize("path", ["test.npy", "test.npz"])
def test_load_calibration_from_paths(path):
    DistanceDetectorCalibration.validate_path(path)


@pytest.mark.parametrize(
    "path,expectation",
    [
        ("test.npy", pytest.raises(ValueError)),
        ("test.npz", does_not_raise()),
    ],
)
def test_save_calibration_from_paths(path, expectation):
    with expectation:
        DistanceDetectorCalibration.validate_path(
            path, file_extensions=[("npz", "Numpy data archives (*.npz)")]
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    sp = subparsers.add_parser("save")

    args = parser.parse_args()

    if args.command == "save":
        for parameter_set in PARAMETER_SETS:
            output = get_output(parameter_set)
            save_output(path_for_parameter_set(parameter_set), output)

        for parameter_set in PARAMETER_SETS_CALIBRATION:
            output = get_output_precalibrated(parameter_set)
            save_output(path_for_parameter_set(parameter_set, calibration=True), output)
    else:
        raise RuntimeError
