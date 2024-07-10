# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

from acconeer.exptool.setup.base import PlatformInstall, SetupGroup, ShellCommandStep, utils

from .linux import Linux


@PlatformInstall.register
class Ubuntu_22_04(Linux):
    def __init__(self) -> None:
        super().__init__()
        self.add_steps(
            utils.WithDescription(
                '> Download dependencies via "apt" that are required '
                + "to run the Exploration tool app.",
                SetupGroup(
                    ShellCommandStep("sudo apt update".split()),
                    ShellCommandStep(
                        "sudo apt install -y libxcb-xinerama0-dev libusb-1.0-0 libxcb-cursor0".split()
                    ),
                ),
            ),
            utils.WithDescription(
                '> Use "apt" to remove modemmanager, this is needed to not interfere with bootloader for some EVKs.',
                SetupGroup(
                    ShellCommandStep("sudo apt purge -y modemmanager".split()),
                ),
            ),
            utils.WithDescription(
                "> Trigger udev to update the permission rules.",
                SetupGroup(
                    ShellCommandStep("sudo udevadm control --reload-rules".split()),
                    ShellCommandStep("sudo udevadm trigger".split()),
                ),
            ),
        )

    @classmethod
    def get_key(cls) -> str:
        return "Ubuntu_22.04"
