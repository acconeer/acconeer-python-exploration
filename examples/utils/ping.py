from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.clients import configs
from acconeer.exptool import example_utils


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = UARTClient(port)

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors

    info = client.connect()
    print("connect info:", info)
    client.start_streaming(config)
    client.get_next()
    client.disconnect()


if __name__ == "__main__":
    main()
