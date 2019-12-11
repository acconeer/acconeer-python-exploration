import os
import sys

from acconeer.exptool import configs, recording, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient


def main():
    parser = utils.ExampleArgumentParser()
    parser.add_argument("-o", "--output-dir", type=str, required=True)
    parser.add_argument("--file-format", type=str, default="h5")
    parser.add_argument("--frames-per-file", type=int, default=10000)
    args = parser.parse_args()
    utils.config_logging(args)

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

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 30

    session_info = client.start_session(config)

    os.makedirs(args.output_dir)

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    total_num_frames = 0
    while not interrupt_handler.got_signal:
        record_count, num_frames_in_record = divmod(total_num_frames, args.frames_per_file)

        if num_frames_in_record == 0:
            recorder = recording.Recorder(sensor_config=config, session_info=session_info)

        data_info, data = client.get_next()
        recorder.sample(data_info, data)

        if num_frames_in_record + 1 == args.frames_per_file:
            record = recorder.close()
            filename = os.path.join(
                args.output_dir, "{:04}.{}".format(record_count + 1, file_format))
            print("Saved", filename)
            recording.save(filename, record)

        total_num_frames += 1
        print("Sampled {:>5}".format(total_num_frames), end="\r", flush=True)

    try:
        client.disconnect()
    except Exception:
        pass

    record_count, num_frames_in_record = divmod(total_num_frames, args.frames_per_file)
    if num_frames_in_record > 0:
        record = recorder.close()
        filename = os.path.join(
            args.output_dir, "{:04}.{}".format(record_count + 1, file_format))
        print("Saved", filename)
        recording.save(filename, record)


if __name__ == "__main__":
    main()
