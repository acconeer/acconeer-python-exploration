import os
import sys

import acconeer.exptool as et


def main():
    args = et.utils.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    filename = "data.h5"
    if os.path.exists(filename):
        print("File '{}' already exists, won't overwrite".format(filename))
        sys.exit(1)

    if args.socket_addr:
        client = et.a111.SocketClient(args.socket_addr)
    elif args.spi:
        client = et.a111.SPIClient()
    else:
        port = args.serial_port or et.utils.autodetect_serial_port()
        client = et.a111.UARTClient(port)

    config = et.a111.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.update_rate = 30

    session_info = client.setup_session(config)

    recorder = et.recording.Recorder(sensor_config=config, session_info=session_info)

    client.start_session()

    n = 100
    for i in range(n):
        data_info, data = client.get_next()
        recorder.sample(data_info, data)
        print("Sampled {:>4}/{}".format(i + 1, n), end="\r", flush=True)

    print()

    client.disconnect()

    record = recorder.close()
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    et.recording.save(filename, record)
    print("Saved to '{}'".format(filename))


if __name__ == "__main__":
    main()
