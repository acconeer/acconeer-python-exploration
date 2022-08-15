# Copyright (c) Acconeer AB, 2022
# All rights reserved

import acconeer.exptool as et


def main():
    args = et.a111.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = et.a111.Client(**et.a111.get_client_args(args))

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
