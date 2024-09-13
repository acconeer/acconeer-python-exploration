# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved


from __future__ import annotations

import abc
import argparse
import json
import typing as t
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple, Union, cast

import numpy as np
import numpy.typing as npt
import pandas as pd

import acconeer.exptool as et
import acconeer.exptool.a121.algo.bilateration as bilateration
import acconeer.exptool.a121.algo.breathing as breathing
import acconeer.exptool.a121.algo.distance as distance
import acconeer.exptool.a121.algo.hand_motion as hand_motion
import acconeer.exptool.a121.algo.obstacle as obstacle
import acconeer.exptool.a121.algo.parking as parking
import acconeer.exptool.a121.algo.phase_tracking as phase_tracking
import acconeer.exptool.a121.algo.presence as presence
import acconeer.exptool.a121.algo.smart_presence as smart_presence
import acconeer.exptool.a121.algo.speed as speed
import acconeer.exptool.a121.algo.surface_velocity as surface_velocity
import acconeer.exptool.a121.algo.tank_level as tank_level
import acconeer.exptool.a121.algo.touchless_button as touchless_button
import acconeer.exptool.a121.algo.vibration as vibration
import acconeer.exptool.a121.algo.waste_level as waste_level
from acconeer.exptool import a121
from acconeer.exptool.a121 import H5Record, _core, algo
from acconeer.exptool.a121._core_ext._replaying_client import _ReplayingClient


try:
    import prettyprinter  # type: ignore[import-not-found]

    prettyprinter.install_extras(["attrs"])

    pprint = prettyprinter.cpprint
except ImportError:
    from pprint import pprint


DESCRIPTION = """This is a command line utility that lets you convert
.h5/.npz files to .csv, .tsv, and .xlsx-files for use as is or in
e.g. Microsoft Excel.

example usage:
  python convert_h5.py my_data_file.h5
  # Using the default python on a personal desktop, this will convert 'my_data_file.h5'
  # that exist in same directory as directory of convert_h5.py python script
  # into an Excel file (.xlsx) format named my_data_file.xlsx with multiple sheets
  # inside of a folder named my_data_file

  python3 convert_h5.py -v C:/Users/Desktop/my_data_file.h5 D:/my_folder/saved_file.csv
  # Using the python 3 version on a personal desktop,
  # this will convert 'my_data_file.h5' from a specified directory
  # into different .csv files in a specified directory,
  # inside of a folder named saved_file
  # instead of all information being in a single file 'saved_file.csv'
  # It also prints the metadata from the input file
"""


class ConvertToCsvArgumentParser(argparse.ArgumentParser):
    def __init__(self) -> None:
        super().__init__(description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)
        self.add_argument(
            "input_path",
            type=Path,
            help='The input file or path with file endings ".h5" or ".npz" (only A111).',
        )
        self.add_argument(
            "output_path",
            type=Path,
            nargs="?",
            default=None,
            help="The output file or path to which h5-data will be written.",
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
            help='Forcefully overwrite "output_path" if it already exists.',
        )
        self.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=False,
            help='Prints meta data from "input_path".',
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
    def convert(self, sensor: int) -> list[npt.NDArray[t.Any]]:
        pass

    @abc.abstractmethod
    def get_metadata_rows(self, sensor: int, as_header: bool) -> list[npt.NDArray[t.Any]]:
        pass

    @abc.abstractmethod
    def get_environment(self) -> dict[str, t.Any]:
        pass

    @abc.abstractmethod
    def get_configs(self, session_index: int = 0) -> dict[str, t.Any]:
        pass

    @abc.abstractmethod
    def get_time(self) -> list[list[str]]:
        pass

    @abc.abstractmethod
    def get_converted_data(self, sensor: int, transpose: bool) -> dict[str, t.Any]:
        pass

    @abc.abstractmethod
    def print_information(self, verbose: bool = False) -> None:
        pass

    @staticmethod
    def format_cell_value(v: t.Any) -> str:
        if isinstance(v, complex):
            return f"{np.real(v):0}{np.imag(v):+}j"
        else:
            return str(v)

    @classmethod
    def record_from_path(
        cls, input_path: Union[Path, str]
    ) -> Union[et.a111.recording.Record, a121.H5Record]:
        try:
            x = a121.open_record(input_path)
            assert isinstance(x, H5Record)
            return x
        except Exception:  # noqa: S110
            pass

        try:
            return et.a111.recording.load(input_path)
        except Exception:  # noqa: S110
            pass

        msg = "The specified file was neither A111 or A121. Cannot load."
        raise Exception(msg)

    @classmethod
    def from_path(cls, input_path: Union[Path, str]) -> TableConverter:
        return cls.from_record(cls.record_from_path(input_path))

    @classmethod
    def from_record(cls, record: Union[et.a111.recording.Record, a121.H5Record]) -> TableConverter:
        if isinstance(record, et.a111.recording.Record):
            return A111RecordTableConverter(record)
        elif isinstance(record, a121.H5Record):
            return A121RecordTableConverter(record)
        else:
            msg = f"Passed record ({record}) was of unexpected type."
            raise ValueError(msg)


class A111RecordTableConverter(TableConverter):
    def __init__(self, record: et.a111.recording.Record) -> None:
        self._record = record

    def get_metadata_rows(self, sensor: int, as_header: bool = False) -> list[t.Any]:
        depths = et.a111.get_range_depths(self._record.sensor_config, self._record.session_info)
        num_points = len(depths)
        rounded_depths = np.round(depths, decimals=6)

        if self._record.mode != et.a111.Mode.SPARSE:
            sweep_numbers = []
            depths_header = rounded_depths.tolist()
        else:
            spf = self._record.sensor_config.sweeps_per_frame
            sweep_numbers = (np.repeat(range(spf), repeats=num_points).astype(int)).tolist()
            depths_header = (np.tile(rounded_depths, spf)).tolist()
        if as_header:
            depths_header = [f"{round(depth, 3)}m" for depth in depths_header]
            sweep_numbers = [f"sweep {sweep_number}" for sweep_number in sweep_numbers]

        return [sweep_numbers, depths_header]

    def convert(self, sensor: int) -> list[npt.NDArray[t.Any]]:
        """Converts data of a single sensor

        :param sensor: The sensor index
        :returns: 2D NDArray of cell values.
        """
        self.sensor = sensor
        record = self._record
        sensor_index = sensor

        num_sensors = record.data.shape[1]
        if sensor_index >= num_sensors:
            msg = (
                f"Invalid sensor index specified (index={sensor_index}). "
                f"Valid indices for this input file is one of {list(range(num_sensors))}"
            )
            raise ValueError(msg)

        data = record.data[:, sensor_index, :]
        dest_rows = []

        for x in data:
            row = np.ndarray.flatten(x)
            dest_rows.append([self.format_cell_value(v) for v in row])

        return [np.array(dest_rows)]

    def get_environment(self) -> dict[str, t.Any]:
        environment_dict = {
            "RSS version": self._record.rss_version,
            "acconeer.exptool library version": self._record.lib_version,
            "mode": self._record.mode,
            "module": self._record.module_key,
            "Timestamp": self._record.timestamp,
        }
        return environment_dict

    def get_configs(self, session_index: int = 0) -> dict[str, t.Any]:
        session_info = self._record.session_info
        sensor_config = self.parse_config_dump(self._record.sensor_config_dump)
        processing_config_dump = self._record.processing_config_dump or ""
        processing_config_dict = self.parse_config_dump(processing_config_dump)

        return {
            **session_info,
            **sensor_config,
            **processing_config_dict,
        }

    def get_time(self) -> list[list[str]]:
        data_time = self._record.sample_times
        converted_times_list = [datetime.fromtimestamp(ts) for ts in data_time]
        formatted_times = [time.strftime("%H:%M:%S.%f")[:-4] for time in converted_times_list]
        return [formatted_times]

    def get_converted_data(self, sensor: int = 0, transpose: bool = False) -> dict[str, t.Any]:
        """This function provide data ready to be added in the excel file.
        The output of this function is a dict where
        :keys   : Sheet name.
        :values : Pandas Dataframe
        :returns: Keys.
        """
        dict_excel_file = {}
        sparse_iq_data = self.convert(sensor)
        metadata_rows = self.get_metadata_rows(sensor=sensor, as_header=True)
        time = self.get_time()
        # Add sparse IQ data in excel
        sparse_id_df = pd.DataFrame(sparse_iq_data[0], columns=metadata_rows[1], index=time[0])
        if transpose:
            sparse_id_df = sparse_id_df.transpose()
        dict_excel_file["Raw data"] = sparse_id_df

        # Add configurations in excel
        configs = self.get_configs()
        dict_excel_file["Configurations"] = pd.DataFrame(configs.items())

        # Create a Pandas DataFrame from the environment
        record_environtment = self.get_environment()
        dict_excel_file["Environtment"] = pd.DataFrame(record_environtment.items())
        return dict_excel_file

    def print_information(self, verbose: bool = False) -> None:
        config = self.get_configs()
        print("=== Session info " + "=" * 43)
        for k, v in config.items():
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

        environtment_a111 = self.get_environment()

        for k, v in environtment_a111.items():
            print("{:.<37} {}".format(k + " ", v))

        if record.note:
            print()
            print("Note: " + str(record.note))

    @staticmethod
    def parse_config_dump(config: str) -> t.Any:
        context = {"null": None, "true": True, "false": False}
        return eval(config, context)


class A121RecordTableConverter(TableConverter):
    def __init__(self, record: a121.H5Record) -> None:
        self._record = record

    def _results_of_sensor_id(
        self, sensor_id: int, group_id: int = 0, session_index: int = 0
    ) -> list[a121.Result]:
        return [
            ext_result[sensor_id]
            for ext_result_group in self._record.session(session_index).extended_results
            for grid, ext_result in enumerate(ext_result_group)
            if sensor_id in ext_result and grid == group_id
        ]

    def _unique_sensor_configs_of_sensor_id(
        self, sensor_id: int, group_id: int = 0, session_index: int = 0
    ) -> list[a121.SensorConfig]:
        # FIXME: this is not a `set` as SensorConfig is not hash-able
        sensor_configs = [
            sensor_config
            for grid, sid, sensor_config in _core.utils.iterate_extended_structure(
                self._record.session(session_index).session_config.groups
            )
            if sid == sensor_id and grid == group_id
        ]
        unique_sensor_configs = []
        for sensor_config in sensor_configs:
            if sensor_config not in unique_sensor_configs:
                unique_sensor_configs.append(sensor_config)
        return unique_sensor_configs

    def _unique_metadatas_of_sensor_id(
        self, sensor_id: int, group_id: int = 0, session_index: int = 0
    ) -> list[a121._core.entities.containers.metadata.Metadata]:
        extended = self._record.session(session_index).session_config.extended
        metadatas = [
            metadata
            for grid, sid, metadata in _core.utils.iterate_extended_structure(
                self._record.session(session_index).extended_metadata
            )
            if sid == sensor_id and grid == group_id
        ]
        unique_metadatas = (
            metadatas if extended else [self._record.session(session_index).metadata]
        )
        return unique_metadatas

    def _get_sparse_iq(
        self, sensor: int, group_id: int = 0, session_index: int = 0
    ) -> npt.NDArray[t.Any]:
        """This function handles the case where the sensor at "sensor ID" is configured
        with a single/multiple `SensorConfig(s)`, possibly in multiple groups.

        :param sensor: The sensor ID.
        :returns: 2D NDArray of cell values.
        """

        # Sensor results as a concatenate results of multiple or single configs
        sensor_results = self._results_of_sensor_id(sensor, group_id, session_index=session_index)
        num_groups = len(
            self._unique_sensor_configs_of_sensor_id(sensor, group_id, session_index=session_index)
        )
        rows = []
        row_values = []
        # Append 2nd, 3rd, ... configs to the same rows or array with 1st frame
        for index, result in enumerate(sensor_results):
            # Flatten the frame and format each value
            frame_values = result.frame.flatten()
            for v in frame_values:
                formatted_value = self.format_cell_value(v)
                row_values.append(formatted_value)

            # Append the row based on the number of configurations
            if (index + 1) % num_groups == 0:
                rows.append(row_values)
                row_values = []

        return np.array(rows)

    def get_environment(self) -> dict[str, t.Any]:
        environment_dict = {
            "RSS version": self._record.server_info.rss_version,
            "Exptool version": self._record.lib_version,
            "Timestamp": self._record.timestamp,
            "UUID": self._record.uuid,
        }
        for session_index in range(self._record.num_sessions):
            # Create a Pandas DataFrame from the data
            environment_dict[f"Number of frames session {session_index}"] = str(
                self._record.session(session_index).num_frames
            )
        return environment_dict

    def get_configs(self, session_index: int = 0) -> dict[str, t.Any]:
        group_configs = {}
        subsweep_config_with_index: Dict[str, t.Any] = {}
        sensor_config_with_index: Dict[str, t.Any] = {}
        session_config = self._record.session(session_index).session_config
        sensor_ids = []
        group_ids = []
        # Create DataFrames from configurations
        for group_id, sensor_id, sensor_config in _core.utils.iterate_extended_structure(
            session_config.groups
        ):
            if sensor_id not in sensor_ids:
                sensor_ids.append(sensor_id)
            if group_id not in group_ids:
                group_ids.append(group_id)
            sensor_config_with_index[f"group_id [{group_id}] sensor_id [{sensor_id}]"] = None
            frame_rate = "Max" if sensor_config.frame_rate is None else sensor_config.frame_rate
            sweep_rate = "Max" if sensor_config.sweep_rate is None else sensor_config.sweep_rate
            group_configs = {
                "sweep_rate": sweep_rate,
                "frame_rate": frame_rate,
            }
            for key, value in sensor_config.to_dict().items():
                if key == "subsweeps":
                    continue  # subsweeps are extended below
                else:
                    sensor_config_with_index[f"{key} [{group_id}] [{sensor_id}]"] = value

            for idx, subsweep in enumerate(sensor_config.subsweeps):
                subsweep_config_with_index[f"SUBSWEEP INDEX [{idx}]"] = None
                # Later will be converted to multiple subsweeps producing multiple rows in excel
                for key, value in subsweep.to_dict().items():
                    if key != "subsweeps":
                        subsweep_config_with_index[f"{key} [{idx}]"] = value

        update_rate = "Max" if session_config.update_rate is None else session_config.update_rate
        configs = {
            "extended": session_config.extended,
            "update_rate": update_rate,
        }
        sensor_ids_dict = {
            "sensor_ids": sensor_ids,
        }
        group_ids_dict = {
            "group_ids": group_ids,
        }
        config_dict = {
            **configs,
            **sensor_ids_dict,
            **group_ids_dict,
            **group_configs,
            **sensor_config_with_index,
            **subsweep_config_with_index,
        }
        return config_dict

    def convert(self, sensor: int = 1) -> list[npt.NDArray[t.Any]]:
        """Converts data of a single sensor

        :param sensor: The sensor index
        :returns: list of 2D NDArray of cell values from every session.
        """
        sparse_iq_list = []
        sensor_ids = self.get_configs()["sensor_ids"]
        group_ids = self.get_configs()["group_ids"]

        # Sensor results as a concatenate results of multiple or single configs
        for session_index in list(range(self._record.num_sessions)):
            for sensor_id in sensor_ids:
                for group_id in group_ids:
                    siq_single_id_multi_group = self._get_sparse_iq(
                        sensor_id, group_id=group_id, session_index=session_index
                    )
                    sparse_iq_list.append(siq_single_id_multi_group)

        return sparse_iq_list

    def get_metadata_rows(self, sensor: int, as_header: bool = False) -> list[t.Any]:
        sensor_ids = self.get_configs()["sensor_ids"]
        group_ids = self.get_configs()["group_ids"]
        sweeps_numbers = []
        depths_headers = []
        for session_index in list(range(self._record.num_sessions)):
            for sensor_id in sensor_ids:
                for group_id in group_ids:
                    sensor_configs = self._unique_sensor_configs_of_sensor_id(
                        sensor_id, group_id=group_id, session_index=session_index
                    )
                    metadatas = self._unique_metadatas_of_sensor_id(
                        sensor_id, group_id=group_id, session_index=session_index
                    )
                    for metadata, sensor_config in zip(metadatas, sensor_configs):
                        depths = algo.get_distances_m(sensor_config, metadata)
                        depths_header = np.tile(depths, sensor_config.sweeps_per_frame)
                        depths_headers.append(depths_header.tolist())
                        for subsweep in sensor_config.subsweeps:
                            sweeps_number = np.repeat(
                                range(sensor_config.sweeps_per_frame), repeats=subsweep.num_points
                            ).astype(int)
                            sweeps_numbers.append(sweeps_number.tolist())
        if as_header:
            sweeps_numbers = [f"sweep {sweep_number}" for sweep_number in sweeps_numbers]
            depths_headers = [
                [f"{round(depth, 3)}m" for depth in depths_header]
                for depths_header in depths_headers
            ]
        return [sweeps_numbers, depths_headers]

    def get_time_single_session(self, session_index: int) -> list[list[str]]:
        # Sensor results as a concatenate results of multiple or single configs
        sensor_ids = self.get_configs()["sensor_ids"]
        group_ids = self.get_configs()["group_ids"]
        initial_timestamp = self._record.timestamp
        initial_time = datetime.strptime(initial_timestamp, "%Y-%m-%dT%H:%M:%S")

        # Sensor results as a concatenate results of multiple or single configs
        formatted_times_multi_sensor = []
        for sensor_id in sensor_ids:
            for group_id in group_ids:
                seconds_list = []
                sensor_results = self._results_of_sensor_id(
                    sensor_id, group_id=group_id, session_index=session_index
                )
                for result in sensor_results:
                    # Take tick_time
                    seconds_list.append(result.tick_time)
                    # Add seconds to the initial time and store the results
                    resulting_times = [
                        initial_time + timedelta(seconds=sec) for sec in seconds_list
                    ]
                    # Format the resulting times to 'HH:MM:SS.s' format
                    formatted_times = [
                        time.strftime("%H:%M:%S.%f")[:-4] for time in resulting_times
                    ]
                formatted_times_multi_sensor.append(formatted_times)
        return formatted_times_multi_sensor

    def get_time(self) -> list[list[str]]:
        # Get time multiple session
        formatted_times_multi_sensor_session = []
        for session_index in list(range(self._record.num_sessions)):
            formatted_times_multi_sensor = self.get_time_single_session(
                session_index=session_index
            )
            formatted_times_multi_sensor_session.extend(formatted_times_multi_sensor)
        return formatted_times_multi_sensor_session

    def get_converted_data(self, sensor: int = 1, transpose: bool = False) -> dict[str, t.Any]:
        """This function provide data ready to be added in the excel file.
        The output of this function is a dict where
        :keys   : Sheet name.
        :values : Pandas Dataframe
        :returns: Keys.
        """
        dict_excel_file = {}
        table_convert_processed_data = A121ProcessedData(self._record)
        sparse_iq_data = self.convert(sensor=sensor)
        metadata_rows = self.get_metadata_rows(sensor=sensor, as_header=True)
        time = self.get_time()
        # Add sparse IQ data in excel

        num_sessions = table_convert_processed_data._record.num_sessions
        session_indexes = list(range(num_sessions))
        for session_index in session_indexes:
            dict_config = self.get_configs(session_index=session_index)
            sensor_ids = list(dict_config["sensor_ids"])
            group_ids = list(dict_config["group_ids"])
            # Add sparse IQ data in excel
            for sensor_id in sensor_ids:
                for group_id in group_ids:
                    counter_index = (
                        session_indexes.index(session_index)
                        + sensor_ids.index(sensor_id)
                        + group_ids.index(group_id)
                    )
                    filename = f"Sparse IQ sesid {session_index} sid {sensor_id} grid {group_id}"
                    sparse_id_df = pd.DataFrame(
                        sparse_iq_data[counter_index],
                        columns=metadata_rows[1][counter_index],
                        index=time[counter_index],
                    )
                    if transpose:
                        sparse_id_df = sparse_id_df.transpose()
                    dict_excel_file[filename] = sparse_id_df

            # Add configurations in excel
            dict_excel_file[f"Configurations session {session_index}"] = pd.DataFrame(
                dict_config.items()
            )
        # Create a Pandas DataFrame from processed data
        df_processed_data, df_app_config = table_convert_processed_data.get_processed_data()

        if len(sensor_ids) > 1 or len(group_ids) > 1:
            df_processed_data.index = pd.Index(time[0])
        else:
            df_processed_data.index = pd.Index(sum(time, []))
        dict_excel_file["Application configurations"] = df_app_config
        dict_excel_file["Processed data"] = df_processed_data
        record_environtment = self.get_environment()
        dict_excel_file["Environtment"] = pd.DataFrame(record_environtment.items())
        return dict_excel_file

    def print_information(self, verbose: bool = False) -> None:
        print("=== Server info " + "=" * 44)
        pprint(self._record.server_info)
        print("=== Client info " + "=" * 44)
        pprint(self._record.client_info)
        for session_index in range(self._record.num_sessions):
            extended = self._record.session(session_index).session_config.extended

            print("=== Session config " + "=" * 41)
            print(self._record.session(session_index).session_config)

            if not verbose:
                print("=" * 60)
                return

            print("=== Meta data " + "=" * 46)
            pprint(
                self._record.session(session_index).extended_metadata
                if extended
                else self._record.session(session_index).metadata
            )

            environtment_a121 = self.get_environment()
            print("environtment_a121 " + str(environtment_a121))

            for k, v in environtment_a121.items():
                print("{:.<37} {}".format(k + " ", v))

            print("=" * 60)


class ArgumentsChecker:
    files_ok: bool = True
    exit_text: str = ""

    def __init__(self, args: argparse.Namespace):
        """For file with path = C:\\Users\\Desktop\\my_file.h5
        These means :
        drive = C
        directory parent = C:\\Users\\Desktop
        filename = my_file.h5
        filestem = my_file
        file suffix = .h5
        """
        self.args = args

        # Check input_path argument
        self.input_path = Path(args.input_path)

        # Check output_file suffix
        self.output_suffix = (
            ".xlsx"
            if args.output_path is None or args.output_path.suffix == ""
            else args.output_path.suffix
        )
        self.output_csv_separator = "\t" if self.output_suffix == ".tsv" else ","

        # Check output_path argument
        if args.output_path is None:
            self.output_path = self.input_path.with_suffix("")
        else:
            self.output_path = args.output_path.with_suffix("")
            # Below will make the output_path similar to input_path if output_path is not defined
            # Instead of similar to convert_h5.py path
            self.output_path = (
                self.output_path
                if (self.output_path.parent) != self.output_path
                else self.input_path.with_name(self.output_path.stem)
            )

        self.verbose = args.verbose
        self.sweep_as_column = args.sweep_as_column

        print(f"Reading from {self.input_path!r} ... \n")

        if not Path.exists(self.input_path):
            self.exit_text = str(f'The input file ("{self.input_path}") can not be found.')
            self.files_ok = False

        if Path.exists(self.output_path) and not args.force:
            exit_text_0 = str(f'The output file ("{self.output_path}") already exists.')
            exit_text_1 = str(
                'Overwrite existing file with "-f" or give different name for output file.'
            )
            self.exit_text = exit_text_0 + "\n" + exit_text_1
            self.files_ok = False
        self.sensor = self.get_default_sensor_id_or_index()

    def get_default_sensor_id_or_index(self) -> int:
        try:
            note_text_0 = str(
                "The file from the A121 results includes results from multiple sessions."
            )
            note_text_1 = str(
                "Specifying the sensor/session id in the arguments does not provide extra information."
            )
            note_text = note_text_0 + "\n" + note_text_1
            print(note_text)
            return int(self.args.sensor)
        except AttributeError:
            return 0


class A121ProcessedData:
    _record: a121.H5Record

    def __init__(self, input_record_or_path: Union[a121.H5Record, Path, str]) -> None:
        if isinstance(input_record_or_path, str):
            input_path = Path(input_record_or_path)
            self._record = self.load_file(input_path)
        elif isinstance(input_record_or_path, Path):
            input_path = input_record_or_path
            self._record = self.load_file(input_path)
        elif isinstance(input_record_or_path, a121.H5Record):
            self._record = input_record_or_path
        self.h5_file = self._record.file
        self.num_frames: int = 0
        for session_index in range(self._record.num_sessions):
            self.num_frames = self.num_frames + self._record.session(session_index).num_frames
        self.client = _ReplayingClient(self._record, realtime_replay=False)
        self.app_key = self.h5_file["algo/key"][()].decode()

    def load_file(self, input_path: Path) -> a121.H5Record:
        try:
            x = a121.open_record(input_path)
            assert isinstance(x, H5Record)
            return x
        except Exception as e:  # noqa: S110
            msg = f"Failed to load file: {input_path}"
            raise RuntimeError(msg) from e

    def get_processed_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        df_app_config = pd.DataFrame()
        df_processed_data = pd.DataFrame()

        load_algo_and_client: Dict[
            str, t.Callable[[], Tuple[Dict[str, list[t.Any]], Dict[str, t.Any]]]
        ] = {
            "breathing": self.get_processed_data_breathing,
            "bilateration": self.get_processed_data_bilateration,
            "distance_detector": self.get_processed_data_distance,
            "obstacle_detector": self.get_processed_data_obstacle,
            "hand_motion": self.get_processed_data_hand_motion,
            "parking": self.get_processed_data_parking,
            "phase_tracking": self.get_processed_data_phase_tracking,
            "presence_detector": self.get_processed_data_presence,
            "smart_presence": self.get_processed_data_smart_presence,
            "speed_detector": self.get_processed_data_speed,
            "surface_velocity": self.get_processed_data_surface_velocity,
            "waste_level": self.get_processed_data_waste_level,
            "tank_level": self.get_processed_data_tank_level,
            "touchless_button": self.get_processed_data_touchless_button,
            "vibration": self.get_processed_data_vibration,
        }

        for key, func in load_algo_and_client.items():
            if key == self.app_key:
                dict_processed_data, dict_app_config = func()
                break
        else:
            no_proc_data = ["Sparse iq only contains sparse iq data and no application config"]
            dict_processed_data = {}
            dict_app_config = {"Config": no_proc_data}

        flattened_config: Dict[t.Any, t.Any] = {}

        # Iterate over each key-value pair in the original dictionary
        for key, value in dict_app_config.items():
            if isinstance(value, dict):
                # Flatten config from a config recursively and convert it into readable table formating
                # e.g. Dict : {.... 'presence_config' : {'intra enable' : True ....}}
                # into Dict : {.... 'presence_config' : None, 'intra enable' : True ....}}
                flattened_config[key] = None
                for sub_key, sub_value in value.items():
                    flattened_config[sub_key] = sub_value
            else:
                # If it's not a dictionary, add it directly to the result
                flattened_config[key] = value
        df_processed_data = pd.DataFrame(dict_processed_data)

        self.client.close()
        print("Disconnecting...")

        # Convert the flattened dictionary to a DataFrame with 'Key' and 'Value' columns
        df_app_config = pd.DataFrame(
            [{"Key": key, "Value": value} for key, value in flattened_config.items()]
        )

        return df_processed_data, df_app_config

    def get_processed_data_parking(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []

        # Record file extraction
        sensor_id, RefAppConfig, RefAppContext = parking._ref_app._load_algo_data(
            self.h5_file["algo"]
        )

        # Create dict from configurations and sensor id
        dict_algo_data = {
            **{"sensor_id": sensor_id},
            **(RefAppConfig.to_dict()),
            **(RefAppContext.to_dict()),
        }

        # Client and aggregator preparation
        ref_app = parking._ref_app.RefApp(
            client=self.client,
            sensor_id=sensor_id,
            ref_app_config=RefAppConfig,
            context=RefAppContext,
        )

        ref_app.start()

        try:
            for idx in range(self.num_frames):
                processed_data = ref_app.get_next()

                # Put the result in row
                processed_data_row = self.parking_result_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                if (idx % int(0.05 * self.num_frames)) == 0:
                    print(f"... {idx / self.num_frames:.0%}")

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        ref_app.stop()

        # Creates DataFrames from processed data and keys
        keys = ["car_detected", "obstruction_detected"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_waste_level(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        processor_config = waste_level._processor._load_algo_data(self.h5_file["algo"])

        # Create dict from configurations and sensor id
        dict_algo_data = {**{"sensor_id": self._record.sensor_id}, **(processor_config.to_dict())}

        # Record file extraction
        sensor_config = self._record.session_config.sensor_config
        metadata = self._record.metadata

        processor = waste_level.Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
        )
        try:
            for idx, result in enumerate(self._record.results):
                processed_data = processor.process(result)

                # Put the result in row
                processed_data_row = self.waste_level_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        # Creates dict from processed data and keys
        keys = ["level_percent", "level_m"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_breathing(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, ref_app_config = breathing._ref_app._load_algo_data(self.h5_file["algo"])

        # Create Dict from configurations and sensor id
        dict_algo_data = {**{"sensor_id": sensor_id}, **(ref_app_config.to_dict())}

        # Client preparation
        ref_app = breathing.RefApp(
            client=self.client, sensor_id=sensor_id, ref_app_config=ref_app_config
        )
        ref_app.start()

        try:
            for idx in range(self.num_frames):
                processed_data = ref_app.get_next()

                # Put the result in row
                processed_data_row = self.breathing_result_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        print("Disconnecting...")

        # Creates DataFrames from processed data and keys
        keys = ["rate", "motion", "presence_dist"]

        # Creates Dict from processed data and keys
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_obstacle(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []

        # Client preparation
        sensor_ids, detector_config, detector_context = obstacle._detector._load_algo_data(
            self.h5_file["algo"]
        )

        # Create Dict from configurations, sensor id, and detector context
        dict_algo_data = {
            **{"sensor_ids": sensor_ids},
            **(detector_config.to_dict()),
            **(detector_context.to_dict()),
        }

        detector = obstacle.Detector(
            client=self.client,
            sensor_ids=sensor_ids,
            detector_config=detector_config,
            context=detector_context,
        )

        detector.start()
        try:
            for idx, results in enumerate(self._record.results):
                processed_data = detector.get_next()

                # Put the result in row
                processed_data_row = self.obstacle_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                if (idx % int(0.05 * self.num_frames)) == 0:
                    print(f"... {idx / self.num_frames:.0%}")

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        # Creates Dict from processed data and keys
        keys = ["close_proximity_trig", "current_velocity"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_bilateration(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []

        (
            sensor_ids,
            detector_config,
            processor_config,
            context,
        ) = bilateration._processor._load_algo_data(self.h5_file["algo"])

        # Create Dict from configurations, sensor id, and detector context
        dict_algo_data = {
            **{"sensor_id": sensor_ids},
            **(detector_config.to_dict()),
            **(processor_config.to_dict()),
        }

        # Client preparation
        detector = distance.Detector(
            client=self.client,
            sensor_ids=sensor_ids,
            detector_config=detector_config,
            context=context,
        )
        session_config = detector.session_config

        processor = bilateration._processor.Processor(
            session_config=session_config, processor_config=processor_config, sensor_ids=sensor_ids
        )

        detector.start()
        try:
            for idx in range(self.num_frames):
                detector_result = detector.get_next()
                processed_data = processor.process(detector_result)

                # Put the result in row
                processed_data_row = self.bilateration_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                if (idx % int(0.05 * self.num_frames)) == 0:
                    print(f"... {idx / self.num_frames:.0%}")

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        # Creates DataFrames from processed data and keys
        keys = ["distances", "points"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_hand_motion(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, ModeHandlerConfig = hand_motion._mode_handler._load_algo_data(
            self.h5_file["algo"]
        )

        # Create DataFrames from configurations, sensor id, and detector context
        dict_algo_data = {**{"sensor_id": sensor_id}, **(ModeHandlerConfig.to_dict())}

        # Client preparation
        aggregator = hand_motion.ModeHandler(
            client=self.client,
            sensor_id=sensor_id,
            mode_handler_config=ModeHandlerConfig,
        )

        aggregator.start()

        print("Press Ctrl-C to end session")
        try:
            for idx in range(self.num_frames):
                processed_data = aggregator.get_next()

                # Put the result in row
                processed_data_row = self.hand_motion_result_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        # Creates DataFrames from processed data and keys
        keys = ["app_mode", "detection_state"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_tank_level(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_ids, config, tank_level_context = tank_level._ref_app._load_algo_data(
            self.h5_file["algo"]
        )

        # Create DataFrames from configurations and sensor id
        dict_algo_data = {
            **{"sensor_ids": sensor_ids},
            **(config.to_dict()),
            **(tank_level_context.to_dict()),
        }

        # Client preparation
        ref_app = tank_level._ref_app.RefApp(
            client=self.client, sensor_id=sensor_ids, config=config, context=tank_level_context
        )
        ref_app.start()

        try:
            for idx in range(self.num_frames):
                processed_data = ref_app.get_next()

                # Put the result in row
                processed_data_row = self.tank_level_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        ref_app.stop()

        # Creates DataFrames from processed data and keys
        keys = ["level", "peak_detected", "peak_status"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_surface_velocity(
        self,
    ) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, ExampleAppConfig = surface_velocity._example_app._load_algo_data(
            self.h5_file["algo"]
        )

        # Create Dict from configurations and sensor id
        dict_algo_data = {**{"sensor_ids": sensor_id}, **(ExampleAppConfig.to_dict())}

        # Client preparation
        example_app = surface_velocity.ExampleApp(
            client=self.client,
            sensor_id=int(sensor_id),
            example_app_config=ExampleAppConfig,
        )
        example_app.start()

        try:
            for idx in range(self.num_frames):
                processed_data = example_app.get_next()

                # Put the result in row
                processed_data_row = self.surface_velocity_result_as_row(
                    processed_data=processed_data
                )
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        example_app.stop()

        # Creates Dict from processed data and keys
        keys = ["estimated_velocity", "distance"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_presence(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, detector_config, detector_context = presence._detector._load_algo_data(
            self.h5_file["algo"]
        )

        detector_context_dict = detector_context.to_dict() if detector_context is not None else {}
        # Create Dict from configurations, sensor id, and detector context
        dict_algo_data = {
            **{"sensor_ids": sensor_id},
            **(detector_config.to_dict()),
            **detector_context_dict,
        }

        # Client preparation
        detector = presence.Detector(
            client=self.client,
            sensor_id=int(sensor_id),
            detector_config=detector_config,
            detector_context=detector_context,
        )
        detector.start()

        try:
            for idx in range(self.num_frames):
                processed_data = detector.get_next()

                # Put the result in row
                processed_data_row = self.presence_result_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        detector.stop()

        # Creates Dict from processed data and keys
        keys = [
            "Presence",
            f"Intra_presence_score_(threshold_{detector_config.intra_detection_threshold:.1f})",
            f"Inter_presence_score_(threshold_{detector_config.inter_detection_threshold:.1f})",
            "Presence_distance",
        ]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_smart_presence(
        self,
    ) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, RefAppConfig, RefAppContext = smart_presence._ref_app._load_algo_data(
            self.h5_file["algo"]
        )

        # Create Dict from configurations, sensor id, and detector context
        dict_algo_data = {
            **{"sensor_ids": sensor_id},
            **(RefAppConfig.to_dict()),
            **(RefAppContext.to_dict()),
        }

        # Client preparation
        ref_app = smart_presence._ref_app.RefApp(
            client=self.client,
            sensor_id=sensor_id,
            ref_app_config=RefAppConfig,
            ref_app_context=RefAppContext,
        )
        ref_app.start()

        print("Press Ctrl-C to end session")

        try:
            for idx in range(self.num_frames):
                processed_data = ref_app.get_next()

                # Put the result in row
                processed_data_row = self.smart_presence_result_as_row(
                    processed_data=processed_data
                )
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        ref_app.stop()

        # Creates Dict from processed data and keys
        keys = [
            "Presence",
            "Intra_presence_score",
            "Inter_presence_score",
        ]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_touchless_button(
        self,
    ) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        processor_config = touchless_button._processor._load_algo_data(self.h5_file["algo"])

        # Create Dict from configurations and sensor id
        dict_algo_data = {**{"sensor_ids": self._record.sensor_id}, **(processor_config.to_dict())}

        # Record file extraction
        sensor_config = self._record.session_config.sensor_config
        metadata = self._record.metadata

        processor = touchless_button.Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
        )

        try:
            for idx, result in enumerate(self._record.results):
                processed_data = processor.process(result)

                # Put the result in row
                processed_data_row = self.touchless_button_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                if (idx % int(0.05 * self.num_frames)) == 0:
                    print(f"... {idx / self.num_frames:.0%}")

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        # Creates DataFrames from processed data and keys
        keys = ["close_result", "far_result"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_vibration(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, example_app_config = vibration._load_algo_data(self.h5_file["algo"])

        # Create Dict from configurations and sensor id
        dict_algo_data = {**{"sensor_ids": sensor_id}, **(example_app_config.to_dict())}

        # Client preparation
        example_app = vibration.ExampleApp(
            client=self.client,
            sensor_id=int(sensor_id),
            example_app_config=example_app_config,
        )
        example_app.start()

        try:
            for idx in range(self.num_frames):
                processed_data = example_app.get_next()

                # Put the result in row
                processed_data_row = self.vibration_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        example_app.stop()

        # Creates DataFrames from processed data and keys
        keys = ["max_displacement", "max_sweep_amplitude", "max_displacement_freq"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_distance(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_ids, detector_config, detector_context = distance._detector._load_algo_data(
            self.h5_file["algo"]
        )

        # Create Dict from configurations, sensor id, and detector context
        dict_algo_data = {
            **{"sensor_ids": sensor_ids},
            **(detector_config.to_dict()),
            **(detector_context.to_dict()),
        }

        # Client preparation
        detector = distance.Detector(
            client=self.client,
            sensor_ids=sensor_ids,
            detector_config=detector_config,
            context=detector_context,
        )
        detector.start()

        try:
            for idx in range(self.num_frames):
                processed_data = detector.get_next()

                # Put the result in row
                processed_data_row = self.distance_result_as_row(
                    processed_data=processed_data, sensor_ids=sensor_ids
                )
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        detector.stop()

        # Creates DataFrames from processed data and keys
        keys = ["distances", "strengths"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def get_processed_data_phase_tracking(
        self,
    ) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        json_string_config = json.loads(self.h5_file["algo/processor_config"][()].decode())
        processor_config = phase_tracking.ProcessorConfig(
            threshold=json_string_config["threshold"]
        )

        # Create Dict from configurations and sensor id
        dict_algo_data = {**{"sensor_ids": self._record.sensor_id}, **(processor_config.to_dict())}

        # Record file extraction
        sensor_config = self._record.session_config.sensor_config
        metadata = self._record.metadata

        processor = phase_tracking.Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            context=phase_tracking.ProcessorContext(),
        )
        try:
            for idx, result in enumerate(self._record.results):
                processed_data = processor.process(result)

                # Put the result in row
                processed_data_row = self.phase_tracking_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        # Creates DataFrames from processed data and keys
        keys = ["peak_loc_m", "real_iq_history", "imag_iq_history"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }
        return dict_processed_data, dict_algo_data

    def get_processed_data_speed(self) -> Tuple[Dict[str, t.List[t.Any]], Dict[str, t.Any]]:
        processed_data_list = []
        sensor_id, detector_config = speed._detector._load_algo_data(self.h5_file["algo"])

        # Create DataFrames from configurations, sensor id, and detector context
        dict_algo_data = {**{"sensor_ids": sensor_id}, **(detector_config.to_dict())}

        # Client preparation
        detector = speed.Detector(
            client=self.client,
            sensor_id=int(sensor_id),
            detector_config=detector_config,
        )
        detector.start()

        try:
            for idx in range(self.num_frames):
                processed_data = detector.get_next()

                # Put the result in row
                processed_data_row = self.speed_result_as_row(processed_data=processed_data)
                processed_data_list.append(processed_data_row)

                # Print progressing time every 5%
                print(f"... {idx / self.num_frames:.0%}") if (
                    idx % int(0.05 * self.num_frames)
                ) == 0 else None

        except KeyboardInterrupt:
            print("Conversion aborted")
        else:
            print("Processing data is finished. . .")

        detector.stop()

        # Creates DataFrames from processed data and keys
        keys = ["speed_per_depth", "max_speed"]
        dict_processed_data = {
            k: v for k, v in zip(keys, [list(row) for row in zip(*processed_data_list)])
        }

        return dict_processed_data, dict_algo_data

    def breathing_result_as_row(self, processed_data: breathing.RefAppResult) -> list[t.Any]:
        no_result = "None"
        rate = (
            no_result
            if processed_data.breathing_result is None
            or processed_data.breathing_result.breathing_rate is None
            else f"{processed_data.breathing_result.breathing_rate:0.2f}"
        )
        motion = (
            no_result
            if processed_data.breathing_result is None
            else f"{processed_data.breathing_result.extra_result.breathing_motion[-1]:0.2f}"
        )
        presence_dist = (
            no_result
            if not processed_data.presence_result.presence_detected
            else f"{processed_data.presence_result.presence_distance:0.2f}"
        )

        return [rate, motion, presence_dist]

    def obstacle_as_row(self, processed_data: obstacle.DetectorResult) -> list[t.Any]:
        close_proximity_trig = processed_data.close_proximity_trig
        current_velocity = processed_data.current_velocity

        return [close_proximity_trig, current_velocity]

    def bilateration_as_row(self, processed_data: bilateration.ProcessorResult) -> list[t.Any]:
        distance = (
            None
            if processed_data.objects_without_counterpart == []
            else processed_data.objects_without_counterpart[0].distance
        )
        points = processed_data.points
        return [distance, points]

    def parking_result_as_row(self, processed_data: parking.RefAppResult) -> list[t.Any]:
        car_detected = processed_data.car_detected
        obstruction_detected = processed_data.obstruction_detected

        return [car_detected, obstruction_detected]

    def phase_tracking_as_row(self, processed_data: phase_tracking.ProcessorResult) -> list[t.Any]:
        peak_loc_m = processed_data.peak_loc_m
        real_iq_history = np.real(processed_data.iq_history[0])
        imag_iq_history = np.imag(processed_data.iq_history[0])

        return [peak_loc_m, real_iq_history, imag_iq_history]

    def surface_velocity_result_as_row(
        self,
        processed_data: surface_velocity.ExampleAppResult,
    ) -> list[t.Any]:
        velocity = f"{processed_data.velocity :.3f}"
        distance_m = f"{processed_data.distance_m :.3f} m"

        return [velocity, distance_m]

    def presence_result_as_row(self, processed_data: presence.DetectorResult) -> list[t.Any]:
        presence_detected = "Presence!" if processed_data.presence_detected else "None"
        intra_presence_score = f"{processed_data.intra_presence_score:.3f}"
        inter_presence_score = f"{processed_data.inter_presence_score:.3f}"
        presence_dist = f"{processed_data.presence_distance:.3f} m"

        return [presence_detected, intra_presence_score, inter_presence_score, presence_dist]

    def smart_presence_result_as_row(
        self, processed_data: smart_presence.RefAppResult
    ) -> list[t.Any]:
        presence_detected = "Presence!" if processed_data.presence_detected else "None"
        intra_presence_score = f"{processed_data.intra_presence_score:.3f}"
        inter_presence_score = f"{processed_data.inter_presence_score:.3f}"

        return [presence_detected, intra_presence_score, inter_presence_score]

    def waste_level_as_row(self, processed_data: waste_level.ProcessorResult) -> list[t.Any]:
        level_percent = f"{processed_data.level_percent}"
        level_m = f"{processed_data.level_m} m"

        return [level_percent, level_m]

    def touchless_button_as_row(
        self, processed_data: touchless_button.ProcessorResult
    ) -> list[t.Any]:
        close_result = False if processed_data.close is None else processed_data.close.detection
        far_result = False if processed_data.far is None else processed_data.far.detection

        return [close_result, far_result]

    def distance_result_as_row(
        self, processed_data: Dict[int, distance._detector.DetectorResult], sensor_ids: list[int]
    ) -> list[t.Any]:
        distances = []
        strengths = []

        for sensor_id in sensor_ids:
            # Explicitly inform the type checker that distances is not None here
            # This will pass mypy checker
            non_null_distances = cast(npt.NDArray[np.float64], processed_data[sensor_id].distances)
            for distance_result in non_null_distances:
                distances.append(distance_result)
            # Explicitly inform the type checker that strengths is not None here
            non_null_strengths = cast(npt.NDArray[np.float64], processed_data[sensor_id].strengths)
            for strength_result in non_null_strengths:
                strengths.append(strength_result)

        return [distances, strengths]

    def hand_motion_result_as_row(
        self, processed_data: hand_motion.ModeHandlerResult
    ) -> list[t.Any]:
        app_mode = processed_data.app_mode
        detection_state = processed_data.detection_state

        return [app_mode, detection_state]

    def speed_result_as_row(self, processed_data: speed._detector.DetectorResult) -> list[t.Any]:
        speed_per_depth = processed_data.speed_per_depth
        max_speed = processed_data.max_speed

        return [speed_per_depth, max_speed]

    def tank_level_as_row(self, processed_data: tank_level._ref_app.RefAppResult) -> list[t.Any]:
        level = processed_data.level
        peak_detected = processed_data.peak_detected
        peak_status = processed_data.peak_status

        return [level, peak_detected, peak_status]

    def vibration_as_row(self, processed_data: vibration.ExampleAppResult) -> list[t.Any]:
        max_displacement = processed_data.max_displacement
        max_sweep_amplitude = processed_data.max_sweep_amplitude
        max_displacement_freq = processed_data.max_displacement_freq

        return [max_displacement, max_sweep_amplitude, max_displacement_freq]


class DataConverter:
    def __init__(self, dict_excel_file: Dict[str, t.Any]):
        """
        Initializes the Excel, Csv, and Tsv-Saver class.

        Parameters:
        dict_excel_file : Dictionary where
        : keys are sheet names
        : values are DataFrames format of converter information.
        """
        self.dict_excel_file = dict_excel_file

    def save_to_file(self, filepath: Union[Path, str]) -> None:
        """
        Saves the DataFrames in the dictionary to an Excel file with multiple sheets.

        Parameters:
        filepath (str): Path of the output file that include
        : folder path (parent)
        : filename (stem)
        : extension (suffix)

        Returns:
        None
        """
        if isinstance(filepath, str):
            filepath = Path(filepath)

        # Get file extension (suffix)
        self.output_stem = filepath.stem
        self.parent_path = filepath.parent / self.output_stem  # Create folder instead of file
        self.output_suffix = filepath.suffix

        # Handle based on file extension
        if self.output_suffix == ".xlsx":
            self._save_to_excel()
        elif self.output_suffix == ".csv":
            self._save_to_csv()
        elif self.output_suffix == ".tsv":
            self._save_to_csv(delimiter="\t")
        else:
            msg = f"Unsupported file format: {self.output_suffix}"
            raise ValueError(msg)

    def _save_to_excel(self) -> None:
        """
        Helper function to save DataFrames to an Excel file.
        """
        # Save the DataFrame to a CSV or excel file
        filepath = self.parent_path / (self.output_stem + self.output_suffix)
        # Write each DataFrame to a separate sheet using to_excel
        # Default example data frame is written as below

        with pd.ExcelWriter(filepath, engine="xlsxwriter") as writer:
            # Write each DataFrame to a separate sheet
            for key, value in self.dict_excel_file.items():
                pd.DataFrame(value).to_excel(
                    writer, sheet_name=key, index_label="Index", header=True
                )
        print(f"Excel file '{filepath.name}' saved successfully.")

    def _save_to_csv(self, delimiter: str = ",") -> None:
        """
        Helper function to save DataFrames to CSV or TSV files.

        Parameters:
        : delimiter (str): The delimiter to use (',' for CSV and '\t' for TSV).

        Returns:
        None
        """
        # Write each DataFrame to a separate sheet using to_csv
        for key, value in self.dict_excel_file.items():
            filepath = self.parent_path / (key + self.output_suffix)
            pd.DataFrame(value).to_csv(
                Path(str(filepath)),
                sep=delimiter,
                index_label="Index",
            )
        print(f"CSV or TSV file '{filepath.name}' saved successfully.")


def main() -> None:
    parser = ConvertToCsvArgumentParser()
    args = parser.parse_args()

    # File checking and formatting from args
    input_args = ArgumentsChecker(args)

    if not (input_args.files_ok):
        # Exit if files files is not ok
        print(input_args.exit_text)
        exit(1)
    else:
        # Create directory if files files is ok
        input_args.output_path.mkdir(parents=True, exist_ok=True)
    sensor = input_args.sensor
    output_suffix = input_args.output_suffix
    output_path = input_args.output_path
    table_converter = TableConverter.from_path(input_args.input_path)
    try:
        dict_excel_file = table_converter.get_converted_data(
            sensor=sensor, transpose=input_args.sweep_as_column
        )
    except Exception as e:
        print(e)
        exit(1)

    table_converter.print_information(verbose=input_args.verbose)
    print()

    # Prepare data and convert to excel, csv, or tsv
    exported_file = DataConverter(dict_excel_file)
    exported_file.save_to_file(filepath=output_path.with_suffix(output_suffix))

    print("Success!")


if __name__ == "__main__":
    main()
