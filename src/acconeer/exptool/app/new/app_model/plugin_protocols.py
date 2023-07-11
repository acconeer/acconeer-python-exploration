# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

import typing as t

from typing_extensions import Protocol

from acconeer.exptool.app.new.backend import GeneralMessage


ViewPluginInterface = t.Any


class PlotPluginInterface(Protocol):
    def handle_message(self, message: GeneralMessage) -> None:
        ...

    def draw(self) -> None:
        ...
