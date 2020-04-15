"""Stub for loading and processing recorded data"""

import argparse
import json

import matplotlib.pyplot as plt
import numpy as np

from acconeer.exptool import recording, utils


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()
    filename = args.filename

    record = recording.load(filename)

    print_record(record)

    if len(record.data.shape) == 3:  # Envelope, IQ, Power bins
        x = np.arange(len(record.data))
        y = utils.get_range_depths(record.sensor_config, record.session_info)
        z = np.abs(record.data[:, 0, :]).T

        fig, ax = plt.subplots()
        ax.pcolormesh(x, y, z)
        ax.set_xlabel("Sweep index")
        ax.set_ylabel("Depth (m)")
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
    print("First data info (first sensor):")

    for k, v in record.data_info[0][0].items():
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


if __name__ == "__main__":
    main()
