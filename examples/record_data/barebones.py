import os
import sys

from acconeer.exptool import configs, recording, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    filename = "data.h5"
    if os.path.exists(filename):
        print("File '{}' already exists, won't overwrite".format(filename))
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

    n = 100
    for i in range(n):
        data_info, data = client.get_next()
        recorder.sample(data_info, data)
        print("Sampled {:>4}/{}".format(i + 1, n), end="\r", flush=True)

    print()

    client.disconnect()

    record = recorder.close()
    recording.save("data.h5", record)
    print("Saved to '{}'".format(filename))


if __name__ == "__main__":
    main()
