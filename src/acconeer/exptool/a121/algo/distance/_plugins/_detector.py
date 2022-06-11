from __future__ import annotations

from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPluginBase,
    DetectorPlotPluginBase,
    DetectorViewPluginBase,
)
from acconeer.exptool.app.new.app_model import Plugin, PluginFamily


class BackendPlugin(DetectorBackendPluginBase):
    pass


class PlotPlugin(DetectorPlotPluginBase):
    pass


class ViewPlugin(DetectorViewPluginBase):
    pass


DISTANCE_DETECTOR_PLUGIN = Plugin(
    key="distance_detector",
    title="Distance detector",
    description="Easily measure distance to objects.",
    family=PluginFamily.DETECTOR,
    backend_plugin=BackendPlugin,  # type: ignore[misc]
    plot_plugin=PlotPlugin,  # type: ignore[misc]
    view_plugin=ViewPlugin,  # type: ignore[misc]
)
