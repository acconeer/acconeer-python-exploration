from __future__ import annotations

import abc


class PlotPlugin(abc.ABC):
    @abc.abstractmethod
    def setup(self) -> None:
        pass

    @abc.abstractmethod
    def teardown(self) -> None:
        pass
