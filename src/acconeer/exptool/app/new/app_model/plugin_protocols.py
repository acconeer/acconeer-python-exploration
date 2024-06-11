# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from typing_extensions import Protocol

from acconeer.exptool.app.new.backend import GeneralMessage


class PlotPluginInterface(Protocol):
    def handle_message(self, message: GeneralMessage) -> None: ...

    def draw(self) -> None: ...
