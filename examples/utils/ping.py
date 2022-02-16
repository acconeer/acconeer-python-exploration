import acconeer.exptool as et


def main():
    args = et.utils.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    if args.socket_addr:
        client = et.a111.SocketClient(args.socket_addr)
    elif args.spi:
        client = et.a111.SPIClient()
    else:
        port = args.serial_port or et.utils.autodetect_serial_port()
        client = et.a111.UARTClient(port)

    config = et.a111.EnvelopeServiceConfig()
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
