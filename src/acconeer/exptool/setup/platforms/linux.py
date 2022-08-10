from __future__ import annotations

import os

from acconeer.exptool.setup.base import PlatformInstall, RequireFileContentStep, ShellCommandStep


@PlatformInstall.register
class Linux(PlatformInstall):
    UDEV_RULE_FILE = "/etc/udev/rules.d/50-ft4222.rules"
    UDEV_RULE = (
        'SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="601c", MODE:="0666"\n'
    )

    def __init__(self) -> None:
        super().__init__()
        self.add_steps(
            ShellCommandStep(f"sudo usermod -a -G dialout {os.environ.get('USER')}".split()),
            RequireFileContentStep(self.UDEV_RULE_FILE, self.UDEV_RULE, sudo=True),
        )

    @classmethod
    def get_key(cls) -> str:
        return "Linux"
