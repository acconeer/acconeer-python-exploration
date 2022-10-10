# Copyright (c) Acconeer AB, 2022
# All rights reserved

import argparse

import numpy as np

from acconeer.exptool import a121


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    filename = args.filename

    record = a121.load_record(filename)

    print_record(record)

    if args.plot:
        plot_record(record)


def print_record(record: a121.Record) -> None:
    estimated_update_rate = 1 / np.diff(record.stacked_results.tick_time).mean()

    print("ET version: ", record.lib_version)
    print("RSS version:", record.server_info.rss_version)
    print("HW name:    ", record.server_info.hardware_name)
    print("Data shape: ", record.frames.shape)
    print("Est. rate:  ", f"{estimated_update_rate:.3f} Hz")
    print("Timestamp:  ", record.timestamp)
    print()
    print(record.session_config)
    print()
    print(record.metadata)
    print()

    first_result = next(record.results)
    print(first_result)


def plot_record(record: a121.Record) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()

    z = abs(record.frames.mean(axis=1)).T
    x = record.stacked_results.tick_time
    x -= x[0]
    y = np.arange(z.shape[0])

    ax.pcolormesh(x, y, z)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Distance point")
    ax.set_title("Mean sweep amplitude")

    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
