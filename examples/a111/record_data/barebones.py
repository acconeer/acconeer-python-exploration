# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import os
import sys

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    filename = "data.h5"
    if os.path.exists(filename):
        print(f"File '{filename}' already exists, won't overwrite")
        sys.exit(1)

    client = et.a111.Client(**et.a111.get_client_args(args))

    config = et.a111.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 30

    session_info = client.setup_session(config)

    recorder = et.a111.recording.Recorder(sensor_config=config, session_info=session_info)

    client.start_session()

    n = 100
    for i in range(n):
        data_info, data = client.get_next()
        recorder.sample(data_info, data)
        print(f"Sampled {i + 1:>4}/{n}", end="\r", flush=True)

    print()

    client.disconnect()

    record = recorder.close()
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    et.a111.recording.save(filename, record)
    print(f"Saved to '{filename}'")


if __name__ == "__main__":
    main()
