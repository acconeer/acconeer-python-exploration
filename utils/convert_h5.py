# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
import argparse
import json
import os
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121 import _core, algo


try:
    import prettyprinter

    prettyprinter.install_extras(["attrs"])

    pprint = prettyprinter.cpprint
except ImportError:
    from pprint import pprint


DESCRIPTION = """This is a command line utility that lets you convert
.h5/.npz files to .csv-files for use as is or in
e.g. Microsoft Excel.

example usage:
  python3 convert_h5.py -v ~/my_data_file.h5 ~/my_output_file.csv
"""


class ConvertToCsvArgumentParser(argparse.ArgumentParser):
    def __init__(self) -> None:
        super().__init__(description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)
        self.add_argument(
            "input_file",
            type=Path,
            help='The input file with file endings ".h5" or ".npz" (only A111).',
        )
        self.add_argument(
            "output_file",
            type=Path,
            nargs="?",
            default=None,
            help="The output file to which h5-data will be written.",
        )
        self.add_argument(
            "--index",
            "--id",
            "--sensor",
            metavar="index/id",
            dest="sensor",
            type=int,
            default=argparse.SUPPRESS,
            help="The sensor index. Gets data from a specific sensor when multiple sensors are "
            "used.",
        )
        self.add_argument(
            "-f",
            "--force",
            action="store_true",
            default=False,
            help='Forcefully overwrite "output_file" if it already exists.',
        )
        self.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=False,
            help='Prints meta data from "input_file".',
        )
        self.add_argument(
            "--sweep-as-column",
            action="store_true",
            default=False,
            help="Stores sweeps as columns instead of rows.\n"
            "The default is to store sweeps as rows.",
        )
        self.add_argument(
            "-m",
            "--add_sweep_metadata",
            action="store_true",
            default=False,
            help="Adds depth and sweep number info to the csv file",
        )


class TableConverter:
    @abc.abstractmethod
    def convert(self, sensor: int) -> np.ndarray:
        pass

    @abc.abstractmethod
    def get_metadata_rows(self, sensor: int) -> list[np.ndarray]:
        pass

    @abc.abstractmethod
    def print_information(self, verbose: bool = False) -> None:
        pass

    @staticmethod
    def format_cell_value(v):
        if np.imag(v):
            return f"{np.real(v):0}{np.imag(v):+}j"
        else:
            return str(v)

    @classmethod
    def from_record(cls, record: Union[et.a111.recording.Record, a121.Record]) -> "TableConverter":
        if isinstance(record, et.a111.recording.Record):
            return A111RecordTableConverter(record)
        elif isinstance(record, a121.Record):
            return A121RecordTableConverter(record)
        else:
            raise ValueError(f"Passed record ({record}) was of unexpected type.")


class A111RecordTableConverter(TableConverter):
    def __init__(self, record: et.a111.recording.Record) -> None:
        self._record = record

    def get_metadata_rows(self, sensor: int) -> list[np.ndarray]:
        depths = et.a111.get_range_depths(self._record.sensor_config, self._record.session_info)
        num_points = len(depths)
        rounded_depths = np.round(depths, decimals=6)

        if self._record.mode != et.a111.Mode.SPARSE:
            return [rounded_depths]
        else:
            spf = self._record.sensor_config.sweeps_per_frame
            sweep_numbers = np.repeat(range(spf), repeats=num_points).astype(int)
            depths_header = np.tile(rounded_depths, spf)
            return [sweep_numbers, depths_header]

    def convert(self, sensor: int) -> np.ndarray:
        """Converts data of a single sensor

        :param sensor: The sensor index
        :returns: 2D NDArray of cell values.
        """
        record = self._record
        sensor_index = sensor

        num_sensors = record.data.shape[1]
        if sensor_index >= num_sensors:
            raise ValueError(
                f"Invalid sensor index specified (index={sensor_index}). "
                f"Valid indices for this input file is one of {list(range(num_sensors))}"
            )

        data = record.data[:, sensor_index, :]
        dest_rows = []

        for x in data:
            row = np.ndarray.flatten(x)
            dest_rows.append([self.format_cell_value(v) for v in row])

        return np.array(dest_rows)

    def print_information(self, verbose: bool) -> None:
        config_dump = self.parse_config_dump(self._record.sensor_config_dump)
        print("=== Session info " + "=" * 43)
        for k, v in config_dump.items():
            print(f"{k:30} {v} ")
        print("=" * 60)
        print()

        if not verbose:
            return

        record = self._record
        print("Mode:", record.mode.name.lower())
        print()
        print(record.sensor_config)
        print()
        print("Session info")

        for k, v in record.session_info.items():
            print("  {:.<35} {}".format(k + " ", v))

        print()
        print("Data shape:", record.data.shape)
        print("Data dtype:", record.data.dtype)
        print()
        print("Last data info (first sensor):")

        for k, v in record.data_info[-1][0].items():
            print("  {:.<35} {}".format(k + " ", v))

        ts = record.sample_times
        if ts is not None and ts.size >= 2:
            print()
            mean_dt = (ts[-1] - ts[0]) / (ts.size - 1)
            mean_f = 1 / mean_dt
            print("Mean sample rate (client side): {:.2f} Hz".format(mean_f))

        print("\n")

        print("Module (processing) key:", record.module_key)

        if record.processing_config_dump is None:
            print("No processing config dump")
        else:
            print("Processing config dump")
            for k, v in json.loads(record.processing_config_dump).items():
                print("  {:.<35} {}".format(k + " ", v))

        print("\n")

        m = {
            "RSS version": record.rss_version,
            "acconeer.exptool library version": record.lib_version,
            "Timestamp": record.timestamp,
        }

        for k, v in m.items():
            print("{:.<37} {}".format(k + " ", v))

        if record.note:
            print()
            print("Note: " + str(record.note))

    @staticmethod
    def parse_config_dump(config: str):
        context = {"null": None, "true": True, "false": False}
        return eval(config, context)


class A121RecordTableConverter(TableConverter):
    def __init__(self, record: a121.Record) -> None:
        self._record = record

    def _results_of_sensor_id(self, sensor_id: int) -> list[a121.Result]:
        return [
            ext_result.get(sensor_id)
            for ext_result_group in self._record.extended_results
            for ext_result in ext_result_group
            if ext_result.get(sensor_id) is not None
        ]

    def _unique_sensor_configs_of_sensor_id(self, sensor_id: int) -> list[a121.SensorConfig]:
        # FIXME: this is not a `set` as SensorConfig is not hash-able
        sensor_configs = [
            sensor_config
            for _, sid, sensor_config in _core.utils.iterate_extended_structure(
                self._record.session_config.groups
            )
            if sid == sensor_id
        ]
        unique_sensor_configs = []
        for sensor_config in sensor_configs:
            if sensor_config not in unique_sensor_configs:
                unique_sensor_configs.append(sensor_config)
        return unique_sensor_configs

    def _convert_single_sensor_config(
        self,
        sensor: int,
    ) -> np.ndarray:
        """This function handles the case where the sensor at "sensor ID" is configured
        with a single unique `SensorConfig`, possibly in multiple groups.

        :param sensor: The sensor ID.
        :returns: 2D NDArray of cell values.
        """
        return np.array(
            [
                [self.format_cell_value(v) for v in result.frame.flatten()]
                for result in self._results_of_sensor_id(sensor)
            ]
        )

    def _convert_multiple_sensor_config(self, sensor: int) -> np.ndarray:
        """
        This function handles the case where the sensor at "sensor ID" is configured
        with a multiple unique `SensorConfig` across groups.

        :param sensor: The sensor ID.
        :returns: 2D NDArray of cell values.
        """
        raise NotImplementedError(
            "This record contains data where a single sensor has multiple configuration through\n"
            + "the use of groups. Exporting this kind of record is not possible at the moment.\n"
            + "\n"
            + "If this is a feature that you are interested in, please get in contact with us!"
        )

    def convert(self, sensor: int) -> np.ndarray:
        """Converts data of a single sensor

        :param sensor: The sensor index
        :returns: 2D NDArray of cell values.
        """
        unique_sensor_configs = self._unique_sensor_configs_of_sensor_id(sensor)

        if len(unique_sensor_configs) == 1:
            return self._convert_single_sensor_config(sensor)

        if len(unique_sensor_configs) > 1:
            return self._convert_multiple_sensor_config(sensor)

        raise ValueError(f"This record contains no data of sensor with id = {sensor}")

    def _get_metadata_rows_single_sensor_config(self, sensor: int) -> list[np.ndarray]:
        (sensor_config,) = self._unique_sensor_configs_of_sensor_id(sensor)
        (metadata,) = (
            meta
            for _, sid, meta in _core.utils.iterate_extended_structure(
                self._record.extended_metadata
            )
            if sid == sensor
        )
        depths, _ = algo.get_distances_m(sensor_config, metadata)

        sweep_numbers = np.repeat(
            range(sensor_config.sweeps_per_frame), repeats=sensor_config.num_points
        ).astype(int)
        depths_header = np.tile(depths, sensor_config.sweeps_per_frame)
        return [sweep_numbers, depths_header]

    def _get_metadata_rows_multiple_sensor_config(self, sensor: int) -> list[np.ndarray]:
        raise NotImplementedError(
            "This record contains data where a single sensor has multiple configuration through\n"
            + "the use of groups. Exporting this kind of record is not possible at the moment.\n"
            + "\n"
            + "If this is a feature that you are interested in, please get in contact with us!"
        )

    def get_metadata_rows(self, sensor: int) -> list[np.ndarray]:
        unique_sensor_configs = self._unique_sensor_configs_of_sensor_id(sensor)

        if len(unique_sensor_configs) == 1:
            return self._get_metadata_rows_single_sensor_config(sensor)
        else:
            return self._get_metadata_rows_multiple_sensor_config(sensor)

    def print_information(self, verbose: bool = False) -> None:
        extended = self._record.session_config.extended

        print("=== Session config " + "=" * 41)
        print(self._record.session_config)

        if not verbose:
            print("=" * 60)
            return

        print("=== Meta data " + "=" * 46)
        pprint(self._record.extended_metadata if extended else self._record.metadata)
        print("=== Server info " + "=" * 44)
        pprint(self._record.server_info)
        print("=== Client info " + "=" * 44)
        pprint(self._record.client_info)
        print("=== Misc. " + "=" * 50)
        print(f"Exptool version:  {self._record.lib_version}")
        print(f"Number of frames: {self._record.num_frames}")
        print(f"Timestamp:        {self._record.timestamp}")
        print(f"UUID:             {self._record.uuid}")

        print("=" * 60)


def _check_files(input_file, output_file, force):
    if not os.path.exists(input_file):
        print(f'The input file ("{input_file}") can not be found.')
        exit(1)

    if os.path.exists(output_file) and not force:
        print(f'The output file ("{output_file}") already exists.')
        print('Overwrite existing file with "-f" or give different name for output file.')
        exit(1)


def load_file(input_file: str) -> tuple[Union[et.a111.recording.Record, a121.Record], str]:
    for loader, generation in [(a121.load_record, "a121"), (et.a111.recording.load, "a111")]:
        try:
            return loader(input_file), generation
        except Exception:
            pass

    raise Exception("The specified file was neither A111 or A121. Cannot load.")


def get_default_sensor_id_or_index(namespace: argparse.Namespace, generation: str) -> int:
    try:
        return namespace.sensor
    except AttributeError:
        return 1 if generation == "a121" else 0


def main():
    parser = ConvertToCsvArgumentParser()
    args = parser.parse_args()

    input_stem = args.input_file.stem
    output_file = args.output_file
    output_suffix = (
        ".xlsx" if output_file is None or output_file.suffix == "" else output_file.suffix
    )
    output_stem = Path(input_stem if output_file is None else output_file.stem)
    output_file = output_stem.with_suffix(output_suffix)

    _check_files(args.input_file, output_file, args.force)
    print(f"Reading from {args.input_file!r} ... \n")
    record, generation = load_file(args.input_file)
    sensor = get_default_sensor_id_or_index(args, generation)

    table_converter = TableConverter.from_record(record)

    try:
        data_table = table_converter.convert(sensor=sensor)
    except Exception as e:
        print(e)
        exit(1)

    table_converter.print_information(verbose=args.verbose)
    print()

    if args.sweep_as_column:
        data_table = data_table.T

    # Create a Pandas DataFrame from the data
    df_data = pd.DataFrame(data_table)

    # Save the DataFrame to a CSV or excel file
    if output_suffix == ".xlsx":
        df_data.to_excel(output_file, sheet_name="Data", index=False, header=True)

    if output_suffix == ".csv":
        df_data.to_csv(output_file, index=False, header=True)

    if output_suffix == ".tsv":
        df_data.to_csv(output_file, index=False, header=True, sep="\t")

    print("Success!")


if __name__ == "__main__":
    main()
