# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import argparse


class ExptoolArgumentParser(argparse.ArgumentParser):
    def __init__(self) -> None:
        super().__init__()

        self.add_argument("--amv", action="store_true")
        self.add_argument(
            "--portable",
            action="store_true",
            help=argparse.SUPPRESS,  # makes option hidden
        )
        self.add_argument(
            "--purge-config",
            action="store_true",
            help="Remove configuration files.",
        )
        self.add_argument(
            "--plugin-module",
            dest="plugin_modules",
            metavar="module",
            action="append",  # "append" => --plugin-module X --plugin-module Y => [X, Y]
            help=(
                "Allows you to load an arbitrary plugin given a python module "
                + "(installed or in your working directory) NOTE! Accepted argument "
                + "is not a path (e.g. not 'my_processor/latest/plugin.py'), it's a "
                + "python module (e.g. 'my_processor.latest.plugin')"
            ),
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
