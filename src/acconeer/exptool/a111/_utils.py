# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from argparse import SUPPRESS, ArgumentParser, Namespace
from typing import Any, Dict

import numpy as np

import acconeer.exptool as et


def get_range_depths(sensor_config: et.configbase.SensorConfig, session_info: dict) -> np.ndarray:
    """Get range depths in meters."""

    range_start = session_info["range_start_m"]
    range_end = range_start + session_info["range_length_m"]

    if sensor_config.mode == et.a111.Mode.SPARSE:
        num_depths = session_info["data_length"] // sensor_config.sweeps_per_frame
    elif sensor_config.mode == et.a111.Mode.POWER_BINS:
        num_depths = session_info["bin_count"]
    else:
        num_depths = session_info["data_length"]

    return np.linspace(range_start, range_end, num_depths)


class ExampleArgumentParser(ArgumentParser):
    def __init__(self, num_sens="+"):
        super().__init__()

        server_group = self.add_mutually_exclusive_group(required=True)
        server_group.add_argument(
            "-u",
            "--uart",
            metavar="port",
            dest="serial_port",
            help="connect via uart (using module protocol by default)",
            nargs="?",
            const="",  # as argparse does not support setting const to None
        )
        server_group.add_argument(
            "-s",
            "--socket",
            metavar="address",
            dest="socket_addr",
            help="connect via socket on given address (using json-based protocol)",
        )
        server_group.add_argument(
            "-spi",
            "--spi",
            dest="spi",
            help="connect via spi (using register-based protocol)",
            action="store_true",
        )

        self.add_argument(
            "--protocol",
            metavar="protocol",
            help='What specific protocol to use. Any of "module", "exploration" or "streaming"',
            choices=["module", "exploration", "streaming"],
            default=SUPPRESS,
        )

        self.add_argument(
            "--sensor",
            metavar="id",
            dest="sensors",
            type=int,
            default=[1],
            nargs=num_sens,
            help="the sensor(s) to use (default: 1)",
        )
        verbosity_group = self.add_mutually_exclusive_group(required=False)
        verbosity_group.add_argument(
            "-v",
            "--verbose",
            action="store_true",
        )
        verbosity_group.add_argument(
            "-vv",
            "--debug",
            action="store_true",
        )
        verbosity_group.add_argument(
            "-q",
            "--quiet",
            action="store_true",
        )


def get_client_args(namespace: Namespace) -> Dict[str, Any]:
    """
    Filters a passed Namespace to extract client-creation related args.

    :returns: dictionary with client-related keyword-arguments.
    """
    result = {}
    ns_dict = {k: v for k, v in vars(namespace).items() if v is not None}

    if "protocol" in ns_dict:
        result["protocol"] = ns_dict["protocol"]

    if "socket_addr" in ns_dict:
        result["host"] = ns_dict["socket_addr"]
        result["link"] = et.a111.Link.SOCKET
        return result

    if "spi" in ns_dict and ns_dict["spi"]:
        result["link"] = et.a111.Link.SPI
        return result

    if "serial_port" in ns_dict:
        if ns_dict["serial_port"] != "":
            result["serial_port"] = ns_dict["serial_port"]
        if "protocol" not in result:
            result["protocol"] = et.a111.Protocol.MODULE
        result["link"] = et.a111.Link.UART
        return result

    return result
