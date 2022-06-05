from __future__ import annotations

from acconeer.exptool.app.new import plugin


class DetectorBackendPluginBase(plugin.BackendPlugin):
    pass


class DetectorPlotPluginBase(plugin.PlotPlugin):
    pass


class DetectorViewPluginBase(plugin.ViewPlugin):
    pass


class ProcessorBackendPluginBase(plugin.BackendPlugin):
    pass


class ProcessorPlotPluginBase(plugin.PlotPlugin):
    pass


class ProcessorViewPluginBase(plugin.ViewPlugin):
    pass
