from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


def main():
    # To simplify the examples, we use a generic argument parser. It
    # lets you choose between UART/socket, set which sensor(s) to use,
    # and the verbosity level of the logging.
    args = example_utils.ExampleArgumentParser().parse_args()

    # Logging is done using the logging module with a logger named
    # acconeer_utils. We call another helper function which sets up the
    # logging according to the verbosity level set in the arguments.
    # -q  or --quiet:   ERROR   (typically not used)
    # default:          WARNING
    # -v  or --verbose: INFO
    # -vv or --debug:   DEBUG
    example_utils.config_logging(args)

    # Pick client depending on whether socket or UART is used. This
    # might change in the future.
    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    # Create a configuration to run on the sensor. A good first choice
    # is the envelope service, so let's pick that one.
    config = configs.EnvelopeServiceConfig()

    # In all examples, we let you set the sensor(s) via the command line
    config.sensor = args.sensors

    # Set the measurement range [meter]
    config.range_interval = [0.2, 0.3]

    # Set the target measurement rate [Hz]
    config.sweep_rate = 10

    # Other configuration options might be available. Check out the
    # example for the corresponding service/detector to see more.

    client.connect()

    # In most cases, explicitly calling connect is not necessary as
    # setup_session below will call connect if not already connected.

    # Set up the session with the config we created. If all goes well,
    # some information/metadata for the configured session is returned.
    session_info = client.setup_session(config)
    print("Session info:\n", session_info, "\n")

    # Now would be the time to set up plotting, signal processing, etc.

    # Start streaming data from the session. This call will block until
    # the sensor has confirmed that streaming has started.
    client.start_streaming()

    # Alternatively, start_streaming can be given the config instead. In
    # that case, the client will call setup_session(config) for you
    # before starting the stream. For example:
    # session_info = client.start_streaming(config)
    # As this will call setup_session in the background, this will also
    # connect if not already connected.

    # In this simple example, we just want to get a couple of sweeps.
    # To get a sweep, call get_next. get_next will block until the sweep
    # is recieved. Some information/metadata is returned together with
    # the data.

    for i in range(3):
        sweep_info, sweep_data = client.get_next()
        print("Sweep {}:\n".format(i+1), sweep_info, "\n", sweep_data, "\n")

    # We're done, stop streaming. All buffered/waiting sweeps are thrown
    # away. This call will block until the sensor has confirmed that
    # streaming/session has ended.
    client.stop_streaming()

    # Calling stop_streaming before disconnect is not necessary as
    # disconnect will call stop_streaming if streaming is started.

    # Remember to always call disconnect to do so gracefully
    client.disconnect()


if __name__ == "__main__":
    main()
