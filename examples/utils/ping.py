from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
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

    client.connect()
    client.disconnect()


if __name__ == "__main__":
    main()
