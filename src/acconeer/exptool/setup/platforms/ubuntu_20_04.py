from __future__ import annotations

from acconeer.exptool.setup.base import PlatformInstall, ShellCommandStep

from .linux import Linux


@PlatformInstall.register
class Ubuntu_20_04(Linux):
    def __init__(self) -> None:
        self.add_steps(
            ShellCommandStep("sudo apt update".split()),
            ShellCommandStep("sudo apt install -y libxcb-xinerama0-dev".split()),
        )

    @classmethod
    def get_key(cls) -> str:
        return "Ubuntu_20.04"
