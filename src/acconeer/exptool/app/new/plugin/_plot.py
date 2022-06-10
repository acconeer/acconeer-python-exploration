from __future__ import annotations

import abc

import pyqtgraph as pg

from acconeer.exptool.app.new.backend import Message


class PlotPlugin(abc.ABC):
    def __init__(self, plot_layout: pg.GraphicsLayout) -> None:
        self.plot_layout = plot_layout

    @abc.abstractmethod
    def handle_message(self, message: Message) -> None:
        pass
