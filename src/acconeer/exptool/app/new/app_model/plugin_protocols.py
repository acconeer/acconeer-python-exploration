# Copyright (c) Acconeer AB, 2022
# All rights reserved

from typing_extensions import Protocol

from acconeer.exptool.app.new.backend import GeneralMessage


class _MessageHandler(Protocol):
    def handle_message(self, message: GeneralMessage) -> None:
        ...


class ViewPluginInterface(_MessageHandler, Protocol):
    pass


class PlotPluginInterface(_MessageHandler, Protocol):
    def draw(self) -> None:
        ...
