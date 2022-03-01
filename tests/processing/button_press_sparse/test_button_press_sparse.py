import tempfile
from pathlib import Path

import h5py
import numpy as np

import acconeer.exptool as et
from acconeer.exptool.a111.algo.button_press_sparse._processor import (
    ProcessingConfiguration,
    Processor,
)


HERE = Path(__file__).parent

TEST_KEYS = ["signal", "detection"]
PARAMETER_SETS = [
    {},
]


def get_output(parameter_set=None):
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

    output = {k: [] for k in TEST_KEYS}

    for data_info, data in input_record:
        result = processor.process(data.squeeze(0), data_info[0])

        for k in TEST_KEYS:
            output[k].append(result[k])

    return {k: np.array(v) for k, v in output.items()}


def save_output(file, output):
    with h5py.File(file, "w") as f:
        for k in TEST_KEYS:
            f.create_dataset(name=k, data=output[k], track_times=False)


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
            assert np.all(expected_arr == actual_arr)
        else:
            assert np.all(np.isclose(expected_arr, actual_arr))


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

    compare_output(saved_output, loaded_output, exact=True)


def test_path_for_parameter_set():
    assert path_for_parameter_set({"foo": "bar"}) == (HERE / "output_foo-bar.h5")


def test_processor_against_reference():
    for parameter_set in PARAMETER_SETS:
        with open(path_for_parameter_set(parameter_set), "rb") as f:
            expected = load_output(f)

        actual = get_output(parameter_set)
        compare_output(expected, actual)


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
    else:
        raise RuntimeError
