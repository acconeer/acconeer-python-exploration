# Copyright (c) Acconeer AB, 2022
# All rights reserved

"""Stub for loading and processing recorded data"""

import argparse
import json

import numpy as np

import acconeer.exptool as et


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    filename = args.filename

    record = et.a111.recording.load(filename)

    print_record(record)

    if not args.plot:
        return

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()

    depths = et.a111.get_range_depths(record.sensor_config, record.session_info)

    if len(record.data.shape) == 3:  # Envelope, IQ, Power bins
        x = np.arange(len(record.data))
        y = depths
        z = np.abs(record.data[:, 0, :]).T

        ax.pcolormesh(x, y, z)
        ax.set_xlabel("Sweep index")
        ax.set_ylabel("Depth (m)")
    else:
        y = np.abs(record.data[:, 0, :, :].mean(axis=1))

        ax.plot(y)
        ax.set_xlabel("Frame index")
        ax.set_ylabel("Mean sweep amplitude")

        ax.legend([f"{d:.2f}" for d in depths], title="Depth")

    fig.tight_layout()
    plt.show()


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
