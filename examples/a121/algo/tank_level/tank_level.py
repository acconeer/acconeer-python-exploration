# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import (
    PeakSortingMethod,
    ReflectorShape,
    ThresholdMethod,
)
from acconeer.exptool.a121.algo.distance._processors import (
    DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE,
    DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE,
)
from acconeer.exptool.a121.algo.tank_level import RefApp
from acconeer.exptool.a121.algo.tank_level._ref_app import RefAppConfig


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    # Setup the configurations
    # Detailed at https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/ref_apps/tank_level.html

    # Sensor selections
    sensor = 1

    # Tank level configurations
    ref_app_config = RefAppConfig(
        start_m=0.03,
        end_m=0.5,
        max_step_length=2,
        max_profile=a121.Profile.PROFILE_2,
        close_range_leakage_cancellation=True,
        signal_quality=20,
        update_rate=None,
        median_filter_length=5,
        num_medians_to_average=5,
        threshold_method=ThresholdMethod.CFAR,
        reflector_shape=ReflectorShape.PLANAR,
        peaksorting_method=PeakSortingMethod.CLOSEST,
        num_frames_in_recorded_threshold=50,
        fixed_threshold_value=DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE,  # float
        fixed_strength_threshold_value=DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE,  # float
        threshold_sensitivity=0.0,  # float
    )

    # End setup configurations

    # Preparation for client
    client = a121.Client.open(**a121.get_client_args(args))

    # Preparation for reference application processor
    ref_app = RefApp(client=client, sensor_id=sensor, config=ref_app_config)
    ref_app.calibrate()
    ref_app.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        processed_data = ref_app.get_next()
        try:
            if processed_data.level is not None:
                print("Tank level result " + str(processed_data.level))
        except et.PGProccessDiedException:
            break

    ref_app.stop()
    client.close()
    print("Disconnecting...")


if __name__ == "__main__":
    main()
