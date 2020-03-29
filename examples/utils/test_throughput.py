from acconeer.exptool import clients, configs, utils


def main():
    args = utils.ExampleArgumentParser().parse_args()
    utils.config_logging(args)

    if args.socket_addr:
        client = clients.SocketClient(args.socket_addr)
    elif args.spi:
        client = clients.SPIClient()
    else:
        port = args.serial_port or utils.autodetect_serial_port()
        client = clients.UARTClient(port)

    config = configs.IQServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.6]
    config.update_rate = 50

    info = client.start_session(config)

    interrupt_handler = utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    fc = utils.FreqCounter(num_bits=(4 * 8 * info["data_length"]))

    while not interrupt_handler.got_signal:
        info, data = client.get_next()
        fc.tick()

    print("\nDisconnecting...")
    client.disconnect()


if __name__ == "__main__":
    main()
