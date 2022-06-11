from __future__ import annotations

from typing import Callable

from acconeer.exptool.app.new import AppModel, BackendPlugin, PlotPlugin, ViewPlugin


class NullAppModel(AppModel):
    class _NullSignal:
        def connect(self, slot: Callable) -> None:
            pass

    sig_notify: _NullSignal
    sig_error: _NullSignal

    def __init__(self) -> None:
        self.sig_notify = self._NullSignal()
        self.sig_error = self._NullSignal()


class DetectorBackendPluginBase(BackendPlugin):
    pass


class DetectorPlotPluginBase(PlotPlugin):
    pass


class DetectorViewPluginBase(ViewPlugin):
    pass


class ProcessorBackendPluginBase(BackendPlugin):
    pass


class ProcessorPlotPluginBase(PlotPlugin):
    pass


class ProcessorViewPluginBase(ViewPlugin):
    pass
