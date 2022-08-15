# Copyright (c) Acconeer AB, 2022
# All rights reserved

import tempfile

import h5py
import numpy as np

import acconeer.exptool as et


class ProcessingTestModule:
    def __init__(self, processor_class, processing_config_class, path, test_keys, parameter_sets):

        self.processor_class = processor_class
        self.processsing_config_class = processing_config_class
        self.path = path
        self.test_keys = test_keys
        self.parameter_sets = parameter_sets

    def get_output(self, parameter_set=None):
        input_record = et.a111.recording.load(self.path / "input.h5")

        processing_config = self.processsing_config_class()

        if parameter_set is not None:
            for k, v in parameter_set.items():
                setattr(processing_config, k, v)

        processor = self.processor_class(
            input_record.sensor_config,
            processing_config,
            input_record.session_info,
        )

        output = {k: [] for k in self.test_keys}

        for data_info, data in input_record:
            if data.shape[0] == 1:
                result = processor.process(data.squeeze(0), data_info[0])
            else:
                result = processor.process(data, data_info[0])
            if result is not None:

                for k in self.test_keys:
                    output[k].append(result[k])

        # Explicit `dtype=float` makes the conversion `None` -> `np.nan`.
        return {k: np.array(v, dtype=float) for k, v in output.items()}

    def save_output(self, file, output):
        with h5py.File(file, "w") as f:
            for k in self.test_keys:
                try:
                    f.create_dataset(name=k, data=output[k], track_times=False, compression="gzip")
                except TypeError as te:
                    raise TypeError(
                        f"Could not create dataset with name: {k}, data={output[k]}"
                    ) from te

    def load_output(self, file):
        output = {}

        with h5py.File(file, "r") as f:
            for k in self.test_keys:
                output[k] = f[k][()]

        return output

    def compare_output(self, expected, actual, exact=False):
        for k in self.test_keys:
            expected_arr = expected[k]
            actual_arr = actual[k]

            if exact:
                assert np.all(np.array_equal(expected_arr, actual_arr, equal_nan=True))
            else:
                assert np.all(np.isclose(expected_arr, actual_arr, equal_nan=True))

    def path_for_parameter_set(self, parameter_set):
        if parameter_set:
            l = sorted(parameter_set.items())
            suffix = "_".join(f"{k}-{v}" for k, v in l)
        else:
            suffix = "default"

        return self.path / f"output_{suffix}.h5"

    def test_path_for_parameter_set(self):
        assert self.path_for_parameter_set({"foo": "bar"}) == (self.path / "output_foo-bar.h5")

    def test_load_save_compare(self):
        temp_file = tempfile.TemporaryFile()

        saved_output = self.get_output()

        self.save_output(temp_file, saved_output)
        loaded_output = self.load_output(temp_file)

        self.compare_output(saved_output, loaded_output, exact=True)

    def test_processor_against_reference(self):
        for parameter_set in self.parameter_sets:
            with open(self.path_for_parameter_set(parameter_set), "rb") as f:
                expected = self.load_output(f)

            actual = self.get_output(parameter_set)
            self.compare_output(expected, actual)

    def run_all_tests(self):
        self.test_load_save_compare()
        self.test_processor_against_reference()
        self.test_path_for_parameter_set()

    def main(self):
        import argparse

        parser = argparse.ArgumentParser()

        subparsers = parser.add_subparsers(dest="command")
        subparsers.required = True

        subparsers.add_parser("save")

        args = parser.parse_args()

        if args.command == "save":
            for parameter_set in self.parameter_sets:
                output = self.get_output(parameter_set)
                self.save_output(self.path_for_parameter_set(parameter_set), output)
        else:
            raise RuntimeError
