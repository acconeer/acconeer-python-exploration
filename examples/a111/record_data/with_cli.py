# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import os
import sys

import acconeer.exptool as et


def main():
    parser = et.a111.ExampleArgumentParser()
    parser.add_argument("-o", "--output-file", type=str, required=True)
    parser.add_argument("-l", "--limit-frames", type=int)
    args = parser.parse_args()
    et.utils.config_logging(args)

    if os.path.exists(args.output_file):
        print(f"File '{args.output_file}' already exists, won't overwrite")
        sys.exit(1)

    _, ext = os.path.splitext(args.output_file)
    if ext.lower() not in [".h5", ".npz"]:
        print(f"Unknown format '{ext}'")
        sys.exit(1)

    if args.limit_frames is not None and args.limit_frames < 1:
        print("Frame limit must be at least 1")
        sys.exit(1)

    client = et.a111.Client(**et.a111.get_client_args(args))

    config = et.a111.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 30

    session_info = client.setup_session(config)

    recorder = et.a111.recording.Recorder(sensor_config=config, session_info=session_info)

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()

    i = 0
    while not interrupt_handler.got_signal:
        data_info, data = client.get_next()
        recorder.sample(data_info, data)

        i += 1

        if args.limit_frames:
            print(f"Sampled {i:>4}/{args.limit_frames}", end="\r", flush=True)

            if i >= args.limit_frames:
                break
        else:
            print(f"Sampled {i:>4}", end="\r", flush=True)

    print()

    client.disconnect()

    record = recorder.close()
    os.makedirs(os.path.dirname(os.path.abspath(args.output_file)), exist_ok=True)
    et.a111.recording.save(args.output_file, record)
    print(f"Saved to '{args.output_file}'")


if __name__ == "__main__":
    main()
