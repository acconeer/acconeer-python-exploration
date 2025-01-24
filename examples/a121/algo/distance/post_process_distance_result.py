# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

import argparse

import h5py
import matplotlib.pyplot as plt

from acconeer.exptool.a121 import H5Record, _ReplayingClient, _StopReplay
from acconeer.exptool.a121.algo.distance import Detector, DetectorContext
from acconeer.exptool.a121.algo.distance._context import detector_context_timeline
from acconeer.exptool.a121.algo.distance._detector import detector_config_timeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file")

    args = parser.parse_args()

    with h5py.File(args.input_file, "r") as file:
        algo_group = file["algo"]

        sensor_ids = algo_group["sensor_ids"][()].tolist()
        detector_config = detector_config_timeline.migrate(
            algo_group["detector_config"][()].decode()
        )
        context_group = algo_group["context"]
        context: DetectorContext = detector_context_timeline.migrate(context_group)

        record = H5Record(file)
        client = _ReplayingClient(record, realtime_replay=False)

        detector = Detector(
            client=client,
            sensor_ids=sensor_ids,
            detector_config=detector_config,
            context=context,
        )

        detector.start()

        fig, axs = plt.subplots(ncols=2, sharex=True)
        fig.set_figwidth(15)

        while True:
            try:
                result = detector.get_next()

                for processor_result in result[sensor_ids[0]].processor_results:
                    axs[0].plot(
                        processor_result.extra_result.distances_m,
                        processor_result.extra_result.abs_sweep,
                        "b",
                    )
                    axs[0].plot(
                        processor_result.extra_result.distances_m,
                        processor_result.extra_result.used_threshold,
                        "r",
                    )

                axs[1].plot(result[sensor_ids[0]].distances, result[sensor_ids[0]].strengths, "k.")
            except _StopReplay:
                break

    axs[0].legend(["Sweep", "Threshold"], loc="upper left")

    axs[0].set_xlabel("Distance (m)")
    axs[0].set_ylabel("Amplitude")
    axs[0].grid()

    axs[1].set_xlabel("Distance (m)")
    axs[1].set_ylabel("Strength")
    axs[1].grid()

    plt.legend()
    plt.suptitle(args.input_file)
    plt.show()


if __name__ == "__main__":
    main()
