from acconeer.exptool import configs, utils
from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = SocketClient(args.socket_addr)
    elif args.spi:
        client = SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = UARTClient(port)

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors

    print(config)

    connect_info = client.connect()
    print("connect info:")
    print_dict(connect_info)

    session_info = client.start_session(config)
    print("session_info:")
    print_dict(session_info)

    data_info, data = client.get_next()
    print("data_info:")
    print_dict(data_info)

    client.disconnect()


def print_dict(d):
    for k, v in d.items():
        print("  {:.<35} {}".format(k + " ", v))


if __name__ == "__main__":
    main()
