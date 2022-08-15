# Copyright (c) Acconeer AB, 2022
# All rights reserved

import os
import sys

import acconeer.exptool as et


def main():
    parser = et.a111.ExampleArgumentParser()
    parser.add_argument("-o", "--output-dir", type=str, required=True)
    parser.add_argument("--file-format", type=str, default="h5")
    parser.add_argument("--frames-per-file", type=int, default=10000)
    args = parser.parse_args()
    et.utils.config_logging(args)

    if os.path.exists(args.output_dir):
        print("Directory '{}' already exists, won't overwrite".format(args.output_dir))
        sys.exit(1)

    file_format = args.file_format.lower()
    if file_format == "np":
        file_format = "npz"

    if file_format not in ["h5", "npz"]:
        print("Unknown format '{}'".format(args.file_format))
        sys.exit(1)

    if args.frames_per_file < 10:
        print("Frames per file must be at least 10")
        sys.exit(1)

    client = et.a111.Client(**et.a111.get_client_args(args))

    config = et.a111.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 30

    session_info = client.start_session(config)

    os.makedirs(args.output_dir)

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    total_num_frames = 0
    while not interrupt_handler.got_signal:
        record_count, num_frames_in_record = divmod(total_num_frames, args.frames_per_file)

        if num_frames_in_record == 0:
            recorder = et.a111.recording.Recorder(sensor_config=config, session_info=session_info)

        data_info, data = client.get_next()
        recorder.sample(data_info, data)

        if num_frames_in_record + 1 == args.frames_per_file:
            record = recorder.close()
            filename = os.path.join(
                args.output_dir, "{:04}.{}".format(record_count + 1, file_format)
            )
            print("Saved", filename)
            et.a111.recording.save(filename, record)

        total_num_frames += 1
        print("Sampled {:>5}".format(total_num_frames), end="\r", flush=True)

    try:
        client.disconnect()
    except Exception:
        pass

    record_count, num_frames_in_record = divmod(total_num_frames, args.frames_per_file)
    if num_frames_in_record > 0:
        record = recorder.close()
        filename = os.path.join(args.output_dir, "{:04}.{}".format(record_count + 1, file_format))
        print("Saved", filename)
        et.a111.recording.save(filename, record)


if __name__ == "__main__":
    main()
