# Copyright (c) Acconeer AB, 2022
# All rights reserved

from argparse import ArgumentParser

from acconeer.exptool.setup.base import PlatformInstall


class SetupArgumentParser(ArgumentParser):
    def __init__(self) -> None:
        super().__init__(
            prog="python -m acconeer.exptool.setup",
            description="Helps you setup your computer for use with Acconeer products.",
        )

        self.add_argument("--platform", choices=PlatformInstall.platforms(), default=None)
        self.add_argument(
            "--silent",
            action="store_true",
            default=False,
            help="Skips printing information and yes/no prompts",
        )
