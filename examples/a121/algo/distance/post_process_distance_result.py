# Copyright (c) Acconeer AB, 2023
# All rights reserved


import h5py
import matplotlib.pyplot as plt

from acconeer.exptool.a121 import H5Record, _ReplayingClient, _StopReplay
from acconeer.exptool.a121.algo.distance import Detector, DetectorConfig, DetectorContext


FILEPATH = ""


def main():
    with h5py.File(FILEPATH, "r") as file:
        algo_group = file["algo"]

        sensor_ids = algo_group["sensor_ids"][()].tolist()
        detector_config = DetectorConfig.from_json(algo_group["detector_config"][()])
        context_group = algo_group["context"]
        context = DetectorContext.from_h5(context_group)

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
    axs[1].set_ylabel("RCS (dBsm)")
    axs[1].grid()

    plt.legend()
    plt.suptitle(FILEPATH)
    plt.show()


if __name__ == "__main__":
    main()
