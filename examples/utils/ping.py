from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    elif args.spi:
        client = RegSPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.sweep_rate = 10

    client.start_streaming(config)
    client.get_next()
    client.disconnect()


if __name__ == "__main__":
    main()
