import argparse
import csv
import json
import os

import numpy as np

import acconeer.exptool as et


DESCRIPTION = """This is a command line utility that lets you convert
.h5/.npz files to .csv-files for use as is or in
e.g. Microsoft Excel.

example usage:
  python3 convert_to_csv.py -v ~/my_data_file.h5 ~/my_output_file.csv
"""


def format_cell_value(v):
    if np.imag(v):
        return f"{np.real(v):0}{np.imag(v):+}j"
    else:
        return str(v)


def parse_config_dump(cfg_str):
    context = {"null": None, "true": True, "false": False}
    return eval(cfg_str, context)


def record_to_csv(
    record: et.a111.recording.Record,
    sensor_index: int = 0,
    sweep_as_column: bool = False,
    add_sweep_metadata: bool = False,
) -> np.ndarray:
    print(record.sensor_config_dump)
    config_dump = parse_config_dump(record.sensor_config_dump)
    print(config_dump)

    print("\nConfiguration")
    for k, v in config_dump.items():
        print(f"{k:30} {v} ")

    num_sensors = record.data.shape[1]
    if sensor_index >= num_sensors:
        raise ValueError(
            f"Invalid sensor index specified (index={sensor_index}). "
            f"Valid indices for this input file is one of {list(range(num_sensors))}"
        )

    # actual translation
    data = record.data[:, sensor_index, :]
    dest_rows = []

    depths = et.a111.get_range_depths(record.sensor_config, record.session_info)

    if record.mode == et.Mode.SPARSE and add_sweep_metadata:
        depths = np.tile(depths, record.sensor_config.sweeps_per_frame)
        sweep_number = np.floor(
            np.linspace(0, record.sensor_config.sweeps_per_frame, num=len(depths), endpoint=False)
        )
        dest_rows.append(sweep_number.astype(int))

    if add_sweep_metadata:
        dest_rows.append(np.round(depths, decimals=6))

    for x in data:
        row = np.ndarray.flatten(x)
        dest_rows.append([format_cell_value(v) for v in row])

    dest = np.array(dest_rows)
    if sweep_as_column:
        dest = dest.T
    return dest


def main():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    _add_arguments(parser)
    args = parser.parse_args()

    input_file = args.input_file
    output_file = args.output_file
    sensor_index = args.index
    force = args.force
    verbose = args.verbose
    delimiter = args.delimiter
    sweep_as_column = args.sweep_as_column
    add_sweep_metadata = args.add_sweep_metadata

    # Convert to real delimiter given to csv module
    if delimiter == "c":
        delimiter = ","
    elif delimiter == "t":
        delimiter = "\t"

    _check_files(input_file, output_file, force)

    print(f'Reading from "{input_file}" ... \n')
    record = et.recording.load(input_file)

    if verbose:
        print("=== Session info " + "=" * 43)
        print_record(record)
        print("=" * 60)
        print()

    try:
        csv_table = record_to_csv(
            record,
            sensor_index=sensor_index,
            sweep_as_column=sweep_as_column,
            add_sweep_metadata=add_sweep_metadata,
        )
        print(f"Writing data with dimensions {csv_table.shape} to {output_file} ...")

        with open(output_file, "w") as f:
            writer = csv.writer(f, delimiter=delimiter)
            for row in csv_table:
                writer.writerow(row)

        print("Success!")
    except ValueError as ve:
        print(ve)
        exit(1)


def _check_files(input_file, output_file, force):
    if not os.path.exists(input_file):
        print(f'The input file ("{input_file}") can not be found.')
        exit(1)

    if os.path.exists(output_file) and not force:
        print(f'The output file ("{output_file}") already exists.')
        print('If you know what you are doing; overwrite it with "-f".')
        exit(1)


def _add_arguments(parser):
    parser.add_argument(
        "-d",
        "--delimiter",
        choices=["c", "t"],
        dest="delimiter",
        default="c",
        help="Delimiter for the output data. Default is comma. 't' is for tab, 'c' for comma",
    )
    parser.add_argument(
        "input_file",
        help='The input file with file endings ".h5" or ".npz".',
    )
    parser.add_argument(
        "output_file",
        help="The output file to which csv-data will be written.",
    )
    parser.add_argument(
        "--index",
        metavar="index",
        dest="index",
        type=int,
        default=0,
        help="The sensor index. Gets data from a specific sensor when multiple sensors are "
        "used (default=0).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        default=False,
        help='Forcefully overwrite "output_file" if it already exists.',
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help='Prints meta data from "input_file".',
    )
    parser.add_argument(
        "--sweep-as-column",
        action="store_true",
        default=False,
        help="Stores sweeps as columns instead of rows.\n"
        "The default is to store sweeps as rows.",
    )
    parser.add_argument(
        "-m",
        "--add_sweep_metadata",
        action="store_true",
        default=False,
        help="Adds depth and sweep number info to the csv file",
    )


def print_record(record):
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


if __name__ == "__main__":
    main()
