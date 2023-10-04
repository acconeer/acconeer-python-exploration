# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.breathing import RefApp
from acconeer.exptool.a121.algo.breathing._ref_app import (
    BreathingProcessorConfig,
    RefAppConfig,
    get_sensor_config,
)
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    # Setup the configurations
    # Detailed at https://docs.acconeer.com/en/latest/exploration_tool/algo/a121/ref_apps/breathing.html

    # Sensor selections
    sensor = 1

    # Ref App Configurations
    breathing_processor_config = BreathingProcessorConfig(
        lowest_breathing_rate=6,
        highest_breathing_rate=60,
        time_series_length_s=20,
    )

    # Presence Configurations
    presence_config = PresenceProcessorConfig(
        intra_detection_threshold=4,
        intra_frame_time_const=0.15,
        inter_frame_fast_cutoff=20,
        inter_frame_slow_cutoff=0.2,
        inter_frame_deviation_time_const=0.5,
    )

    # Breathing Configurations
    ref_app_config = RefAppConfig(
        use_presence_processor=True,
        num_distances_to_analyze=3,
        distance_determination_duration=5,
        breathing_config=breathing_processor_config,
        presence_config=presence_config,
    )

    # End setup configurations

    # Preparation for client
    sensor_config = get_sensor_config(ref_app_config=ref_app_config)
    client = a121.Client.open(**a121.get_client_args(args))
    client.setup_session(sensor_config)

    # Preparation for reference application processor
    ref_app = RefApp(client=client, sensor_id=sensor, ref_app_config=ref_app_config)
    ref_app.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        processed_data = ref_app.get_next()
        try:
            print("Breathing result " + str(processed_data.breathing_result))
        except et.PGProccessDiedException:
            break

    ref_app.stop()
    print("Disconnecting...")
    client.close()


if __name__ == "__main__":
    main()
