# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import os

from acconeer.exptool.setup.base import (
    PlatformInstall,
    RequireFileContentStep,
    ShellCommandStep,
    utils,
)


@PlatformInstall.register
class Linux(PlatformInstall):
    FT4222_UDEV_RULE_FILE = "/etc/udev/rules.d/50-ft4222.rules"
    FT4222_UDEV_RULE = (
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="601c", MODE:="0666"\n'
    )

    XC120_UDEV_RULE_FILE = "/etc/udev/rules.d/50-xc120.rules"
    XC120_UDEV_RULE = (
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a41d", MODE:="0666"\n'
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a42c", MODE:="0666"\n'
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a42d", MODE:="0666"\n'
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="a449", MODE:="0666"\n'
    )

    def __init__(self) -> None:
        super().__init__(
            utils.WithDescription(
                "> Setup up permissions needed for UART communication "
                + "by adding the current user to the 'dialout' group.",
                ShellCommandStep(f"sudo usermod -a -G dialout {os.environ.get('USER')}".split()),
            ),
            utils.WithDescription(
                "> Create an udev rule for SPI communication with XM112.",
                RequireFileContentStep(
                    self.FT4222_UDEV_RULE_FILE, self.FT4222_UDEV_RULE, sudo=True
                ),
            ),
            utils.WithDescription(
                "> Create an udev rule for USB communication with XC120.",
                RequireFileContentStep(self.XC120_UDEV_RULE_FILE, self.XC120_UDEV_RULE, sudo=True),
            ),
        )

    @classmethod
    def get_key(cls) -> str:
        return "Linux"
