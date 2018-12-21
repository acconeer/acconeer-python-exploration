from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


def main():
    args = example_utils.ExampleArgumentParser().parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    # Normally when using a single sensor, get_next will return
    # (info, data). When using mulitple sensors, get_next will return
    # lists of info and data for each sensor, i.e. ([info], [data]).
    # This is commonly called squeezing. To disable squeezing, making
    # get_next _always_ return lists, set:
    # client.squeeze = False

    config = configs.EnvelopeServiceConfig()
    config.sensor = args.sensors
    config.range_interval = [0.2, 0.3]
    config.sweep_rate = 5

    session_info = client.setup_session(config)
    print("Session info:\n", session_info, "\n")

    # Now would be the time to set up plotting, signal processing, etc.

    client.start_streaming()

    # Normally, hitting Ctrl-C will raise a KeyboardInterrupt which in
    # most cases immediately terminates the script. This often becomes
    # an issue when plotting and also doesn't allow us to disconnect
    # gracefully. Setting up an ExampleInterruptHandler will capture the
    # keyboard interrupt signal so that a KeyboardInterrupt isn't raised
    # and we can take care of the signal ourselves. In case you get
    # impatient, hitting Ctrl-C a couple of more times will raise a
    # KeyboardInterrupt which hopefully terminates the script.
    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session\n")

    while not interrupt_handler.got_signal:
        info, data = client.get_next()
        print(info, "\n", data, "\n")

    print("Disconnecting...")
    client.disconnect()


if __name__ == "__main__":
    main()
