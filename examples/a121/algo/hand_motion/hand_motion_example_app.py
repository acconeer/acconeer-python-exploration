# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.hand_motion import (
    AppMode,
    DetectionState,
    ModeHandler,
    ModeHandlerConfig,
)


sensor_id = 1


def main():
    client = a121.Client.open()

    config = ModeHandlerConfig()

    aggregator = ModeHandler(
        client=client,
        sensor_id=sensor_id,
        mode_handler_config=config,
    )

    aggregator.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = aggregator.get_next()

        if result.app_mode == AppMode.PRESENCE:
            print("No presence detected")
        elif result.app_mode == AppMode.HANDMOTION:
            if result.example_app_result.detection_state == DetectionState.NO_DETECTION:
                print("No hand motion detected")
            elif result.example_app_result.detection_state == DetectionState.RETENTION:
                print("Retaining detection")
            elif result.example_app_result.detection_state == DetectionState.DETECTION:
                print("Hand motion detected")
            else:
                raise RuntimeError("Invalid detection state")

    print("Disconnecting...")


if __name__ == "__main__":
    main()
