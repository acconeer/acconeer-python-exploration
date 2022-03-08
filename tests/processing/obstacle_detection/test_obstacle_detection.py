import tempfile
from pathlib import Path

import attrs
import h5py
import numpy as np
import pytest
import yaml

import acconeer.exptool as et
from acconeer.exptool.a111.algo.obstacle_detection import ProcessingConfiguration, Processor
from acconeer.exptool.a111.algo.obstacle_detection.calibration import ObstacleDetectionCalibration


HERE = Path(__file__).parent
TEST_KEYS = [
    "env_ampl",
    "peak_idx",
    "angle",
    "velocity",
    "peaks_found",
]
PARAMETER_SETS = [
    {},
]


def get_bg_parameters(parameter_set=None):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()

    if parameter_set is not None:
        for k, v in parameter_set.items():
            processing_config[k]["value"] = v

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
    )

    calibrations = []

    for data_info, data in input_record:
        if data.shape[0] == 1:
            result = processor.process(data.squeeze(0), data_info[0])
        else:
            result = processor.process(data, data_info[0])
        if "new_calibration" in result:
            calibrations.append(result["new_calibration"])

    assert len(calibrations) == 1

    return attrs.asdict(calibrations[0])


def get_output_for_calib(parameter_set=None):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()
    calibration = ObstacleDetectionCalibration.load(HERE / "obstacle_bg_params_dump.yaml")

    if parameter_set is not None:
        for k, v in parameter_set.items():
            processing_config[k]["value"] = v

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
        calibration,
    )

    output = {k: [] for k in TEST_KEYS}

    for data_info, data in input_record:

        if data.shape[0] == 1:
            result = processor.process(data.squeeze(0), data_info[0])
        else:
            result = processor.process(data, data_info[0])

        assert "new_calibration" not in result

        for k in TEST_KEYS:
            output[k].append(result[k])

    # Explicit `dtype=float` makes the conversion `None` -> `np.nan`.
    return {k: np.array(v, dtype=float) for k, v in output.items()}


def get_output(parameter_set=None):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()

    if parameter_set is not None:
        for k, v in parameter_set.items():
            processing_config[k]["value"] = v

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
    )

    output = {k: [] for k in TEST_KEYS}

    for data_info, data in input_record:
        if data.shape[0] == 1:
            result = processor.process(data.squeeze(0), data_info[0])
        else:
            result = processor.process(data, data_info[0])

        for k in TEST_KEYS:
            output[k].append(result[k])

    # Explicit `dtype=float` makes the conversion `None` -> `np.nan`.
    return {k: np.array(v, dtype=float) for k, v in output.items()}


def save_output(file, output):
    with h5py.File(file, "w") as f:
        for k in TEST_KEYS:
            try:
                f.create_dataset(name=k, data=output[k], track_times=False, compression="gzip")
            except TypeError as te:
                raise TypeError(
                    f"Could not create dataset with name: {k}, data={output[k]}"
                ) from te


def load_output(file):
    output = {}

    with h5py.File(file, "r") as f:
        for k in TEST_KEYS:
            output[k] = f[k][()]

    return output


def compare_dicts(expected, actual, keys={}, exact=False) -> bool:
    if not keys:
        keys = expected.keys()
        assert expected.keys() == actual.keys()

    result = True
    for key in keys:
        expected_val = expected[key]
        actual_val = actual[key]

        if exact:
            result = result and np.all(expected_val == actual_val)
        else:
            result = result and np.allclose(expected_val, actual_val, equal_nan=True)

    return result


def compare_output(expected, actual, exact=False):
    assert compare_dicts(expected, actual, TEST_KEYS, exact)


def path_for_parameter_set(parameter_set):
    if parameter_set:
        l = sorted(parameter_set.items())
        suffix = "_".join(f"{k}-{v}" for k, v in l)
    else:
        suffix = "default"

    return HERE / f"output_{suffix}.h5"


def test_load_save_compare():
    temp_file = tempfile.TemporaryFile()

    saved_output = get_output()

    save_output(temp_file, saved_output)
    loaded_output = load_output(temp_file)

    compare_output(saved_output, loaded_output)


def test_path_for_parameter_set():
    assert path_for_parameter_set({"foo": "bar"}) == (HERE / "output_foo-bar.h5")


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_processor_against_reference(parameter_set):
    with open(path_for_parameter_set(parameter_set), "rb") as f:
        expected = load_output(f)

    actual = get_output(parameter_set)
    compare_output(expected, actual)


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_dumped_parameters(parameter_set):
    actual_dict = get_bg_parameters(parameter_set)

    with open(HERE / "obstacle_bg_params_dump.yaml") as stream:
        expected_dict = yaml.safe_load(stream)

    assert compare_dicts(expected_dict, actual_dict)


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_wrong_dumped_parameters(parameter_set):
    actual_dict = get_bg_parameters(parameter_set)

    with open(HERE / "obstacle_bg_params_dump_wrong.yaml") as stream:
        wrong_dict = yaml.safe_load(stream)

    assert actual_dict.keys() == wrong_dict.keys()

    assert not compare_dicts(actual_dict, wrong_dict)


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_setting_calibration_yeilds_expected_results(parameter_set):
    path = path_for_parameter_set(parameter_set).as_posix().replace(".h5", "_calib.h5")
    with open(path, "rb") as f:
        expected = load_output(f)

    actual = get_output_for_calib(parameter_set)
    assert compare_dicts(actual, expected)


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_calibration_instantiated_processor_does_not_return_new_calibration(parameter_set):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()
    calibration = ObstacleDetectionCalibration.load(HERE / "obstacle_bg_params_dump.yaml")

    for k, v in parameter_set.items():
        processing_config[k]["value"] = v

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
        calibration,
    )

    for data_info, data in input_record:
        result = processor.process(data, data_info[0])
        assert "new_calibration" not in result


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_update_calibration_actually_updates(parameter_set):
    input_record = et.a111.recording.load(HERE / "input.h5")

    processing_config = ProcessingConfiguration()
    calibration = ObstacleDetectionCalibration.load(HERE / "obstacle_bg_params_dump.yaml")
    wrong_calibration = ObstacleDetectionCalibration.load(
        HERE / "obstacle_bg_params_dump_wrong.yaml"
    )

    if parameter_set is not None:
        for k, v in parameter_set.items():
            processing_config[k]["value"] = v

    processor = Processor(
        input_record.sensor_config,
        processing_config,
        input_record.session_info,
    )

    for _ in range(10):
        processor.update_calibration(wrong_calibration)
    processor.update_calibration(calibration)

    output = {k: [] for k in TEST_KEYS}

    for data_info, data in input_record:

        if data.shape[0] == 1:
            result = processor.process(data.squeeze(0), data_info[0])
        else:
            result = processor.process(data, data_info[0])

        assert "new_calibration" not in result

        for k in TEST_KEYS:
            output[k].append(result[k])

    # Explicit `dtype=float` makes the conversion `None` -> `np.nan`.
    actual = {k: np.array(v, dtype=float) for k, v in output.items()}

    path = path_for_parameter_set(parameter_set).as_posix().replace(".h5", "_calib.h5")
    with open(path, "rb") as f:
        expected = load_output(f)

    assert compare_dicts(actual, expected)


@pytest.mark.parametrize("parameter_set", PARAMETER_SETS)
def test_preloaded_bg_params(parameter_set):
    actual = get_output_for_calib(parameter_set)

    path = path_for_parameter_set(parameter_set).as_posix().replace(".h5", "_calib.h5")
    with open(path, "rb") as f:
        expected = load_output(f)

    assert compare_dicts(actual, expected)


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

        for parameter_set in PARAMETER_SETS:
            output = get_output_for_calib(parameter_set)
            save_output(
                path_for_parameter_set(parameter_set).as_posix().replace(".h5", "_calib.h5"),
                output,
            )
    else:
        raise RuntimeError
