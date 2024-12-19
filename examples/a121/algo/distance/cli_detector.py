# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import Detector, DetectorConfig, ThresholdMethod


SENSOR_ID = 1


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))
    # DetectorConfig(start_m=0.0, end_m=2.0, max_step_length=12, max_profile=<Profile.PROFILE_1: 1>, close_range_leakage_cancellation=False, signal_quality=15.0, threshold_method=<ThresholdMethod.RECORDED: 4>, peaksorting_method=<PeakSortingMethod.STRONGEST: 2>, reflector_shape=<ReflectorShape.GENERIC: 4>, num_frames_in_recorded_threshold=100, fixed_threshold_value=100.0, fixed_strength_threshold_value=0.0, threshold_sensitivity=0.5, update_rate=50.0)
    # {"start_m": 0.05, "end_m": 0.15, "max_step_length": 1, "max_profile": "PROFILE_1", "close_range_leakage_cancellation": false, "signal_quality": 24.2, "threshold_method": "FIXED_STRENGTH", "peaksorting_method": "CLOSEST", "reflector_shape": "GENERIC", "num_frames_in_recorded_threshold": 100, "fixed_threshold_value": 500.0, "fixed_strength_threshold_value": -30.0, "threshold_sensitivity": 0.5, "update_rate": 50.0}
    detector_config = DetectorConfig(
        start_m=0.05,
        end_m=1.0,
        max_profile=a121.Profile.PROFILE_1,
        max_step_length=1,
        close_range_leakage_cancellation=False,
        signal_quality=24.2,
        threshold_method=a121.algo.distance.ThresholdMethod.FIXED_STRENGTH,
        peaksorting_method=a121.algo.distance.PeakSortingMethod.CLOSEST,
        fixed_threshold_value=500.0,
        fixed_strength_threshold_value=-30.0,
    )

    detector = Detector(client=client, sensor_ids=[SENSOR_ID], detector_config=detector_config)

    detector.calibrate_detector()
    print("Detector calibrated")

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        input("Press enter for next reading")
        detector.start()
        detector_result = detector.get_next()
        try:
            result = detector_result[SENSOR_ID]
            if len(result.distances) != 0:
                print("Temperature " + str(result.temperature)+" Distance " + str(result.distances[0]))
            else:
                print("Result is empty!")
        except et.PGProccessDiedException:
            break
        detector.stop()

    print("Disconnecting...")
    client.close()


if __name__ == "__main__":
    main()
