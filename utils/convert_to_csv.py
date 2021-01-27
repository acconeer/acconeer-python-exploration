import argparse
import csv
import os

import numpy as np

import acconeer.exptool as et

from load_record import print_record


DESCRIPTION = """This is a command line utility that lets you convert
.h5/.npz files to .csv-files for use as is or in
e.g. Microsoft Excel.

example usage:
  python3 convert_to_csv.py -v ~/my_data_file.h5 ~/my_output_file.csv
"""


def record_to_csv(
    record: et.recording.Record, *, index: int = 0, sweep_as_column: bool = False
) -> np.ndarray:
    # early quits
    if record.mode == et.Mode.SPARSE:
        raise ValueError("Sparse data cannot be converted to CSV.")

    num_sensors = record.data.shape[1]
    if index >= num_sensors:
        raise ValueError(
            f"Invalid sensor index specified (index={index}). "
            f"Valid indices for this input file is one of {list(range(num_sensors))}"
        )

    # actual translation
    data = record.data[:, index, :]
    if sweep_as_column:
        data = data.T
    dest = np.empty(data.shape, dtype=object)

    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            real = data[row, col].real
            imag = data[row, col].imag
            if imag == 0:
                cell_str = str(real)
            else:
                cell_str = f"{real:+}{imag:+}j"
            dest[row, col] = cell_str
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
    index = args.index
    force = args.force
    verbose = args.verbose
    sweep_as_column = args.sweep_as_column

    _check_files(input_file, output_file, force)

    print(f'Reading from "{input_file}" ... \n')
    record = et.recording.load(input_file)

    if verbose:
        print("=== Session info " + "=" * 43)
        print_record(record)
        print("=" * 60)
        print()

    try:
        csv_table = record_to_csv(record, index=index, sweep_as_column=sweep_as_column)
        print(f"Writing data with dimensions {csv_table.shape} to {output_file} ...")

        with open(output_file, "w") as f:
            writer = csv.writer(f)
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


if __name__ == "__main__":
    main()
