# Copyright (c) Acconeer AB, 2022
# All rights reserved

import acconeer.exptool as et


def main():
    # To simplify the examples, we use a generic argument parser. It
    # lets you choose between UART/SPI/socket, set which sensor(s) to
    # use, and the verbosity level of the logging.
    args = et.a111.ExampleArgumentParser().parse_args()

    # The client logs using the logging module with a logger named
    # acconeer.exptool.*. We call another helper function which sets up
    # the logging according to the verbosity level set in the arguments:
    # -q  or --quiet:   ERROR   (typically not used)
    # default:          WARNING
    # -v  or --verbose: INFO
    # -vv or --debug:   DEBUG
    et.utils.config_logging(args)

    # Pick client depending on whether socket, SPI, or UART is chosen
    # from the command line.
    client = et.a111.Client(**et.a111.get_client_args(args))

    # Create a configuration to run on the sensor. A good first choice
    # is the envelope service, so let's pick that one.
    config = et.a111.EnvelopeServiceConfig()

    # In all examples, we let you set the sensor(s) via the command line
    config.sensor = args.sensors

    # Set the measurement range [meter]
    config.range_interval = [0.2, 0.3]

    # Set the target measurement rate [Hz]
    config.update_rate = 10

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

    # Start the session. This call will block until the sensor has
    # confirmed that it has started.
    client.start_session()

    # Alternatively, start_session can be given the config instead. In
    # that case, the client will call setup_session(config) for you
    # before starting the session. For example:
    # session_info = client.start_session(config)
    # As this will call setup_session in the background, this will also
    # connect if not already connected.

    # In this simple example, we just want to get a couple of sweeps.
    # To get a sweep, call get_next. get_next will block until the sweep
    # is recieved. Some information/metadata is returned together with
    # the data.

    for i in range(3):
        data_info, data = client.get_next()
        print("Sweep {}:\n".format(i + 1), data_info, "\n", data, "\n")

    # We're done, stop the session. All buffered/waiting data is thrown
    # away. This call will block until the server has confirmed that the
    # session has ended.
    client.stop_session()

    # Calling stop_session before disconnect is not necessary as
    # disconnect will call stop_session if a session is started.

    # Remember to always call disconnect to do so gracefully
    client.disconnect()


if __name__ == "__main__":
    main()
