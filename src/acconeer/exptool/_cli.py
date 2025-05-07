# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Any, Dict


class ExampleArgumentParser(ArgumentParser):
    def __init__(self) -> None:
        super().__init__()

        server_group = self.add_mutually_exclusive_group(required=False)
        server_group.add_argument(
            "--serial-port",
            dest="serial_port",
            metavar="port",
        )
        server_group.add_argument(
            "--ip-address",
            dest="ip_address",
            metavar="address",
        )
        server_group.add_argument(
            "--usb-device",
            dest="usb_device",
            metavar="serial_number",
            nargs="?",
            const=True,
        )
        server_group.add_argument(
            "--mock",
            dest="mock",
            default=None,
            action="store_true",
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

    CLIENT_RELATED_KEYS = ["ip_address", "serial_port", "usb_device", "mock"]
    return {k: getattr(namespace, k) for k in CLIENT_RELATED_KEYS if hasattr(namespace, k)}
