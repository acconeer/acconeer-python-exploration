from __future__ import annotations

from acconeer.exptool.app.new import BackendPlugin, ViewPlugin

from ._a121 import A121PlotPluginBase


class DetectorBackendPluginBase(BackendPlugin):
    pass


class DetectorPlotPluginBase(A121PlotPluginBase):
    pass


class DetectorViewPluginBase(ViewPlugin):
    pass
