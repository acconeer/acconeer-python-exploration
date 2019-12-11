import os
import sys

from acconeer.exptool import configs, recording, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient


def main():
    parser = utils.ExampleArgumentParser()
    parser.add_argument("-o", "--output-file", type=str, required=True)
    parser.add_argument("-l", "--limit-frames", type=int)
    args = parser.parse_args()
    utils.config_logging(args)

    if os.path.exists(args.output_file):
        print("File '{}' already exists, won't overwrite".format(args.output_file))
        sys.exit(1)

    _, ext = os.path.splitext(args.output_file)
    if ext.lower() not in [".h5", ".npz"]:
        print("Unknown format '{}'".format(ext))
        sys.exit(1)

    if args.limit_frames is not None and args.limit_frames < 1:
        print("Frame limit must be at least 1")
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

    session_info = client.setup_session(config)

    recorder = recording.Recorder(sensor_config=config, session_info=session_info)

    client.start_session()

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    i = 0
    while not interrupt_handler.got_signal:
        data_info, data = client.get_next()
        recorder.sample(data_info, data)

        i += 1

        if args.limit_frames:
            print("Sampled {:>4}/{}".format(i, args.limit_frames), end="\r", flush=True)

            if i >= args.limit_frames:
                break
        else:
            print("Sampled {:>4}".format(i), end="\r", flush=True)

    print()

    client.disconnect()

    record = recorder.close()
    recording.save(args.output_file, record)
    print("Saved to '{}'".format(args.output_file))


if __name__ == "__main__":
    main()
