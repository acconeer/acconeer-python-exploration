from __future__ import annotations

from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPlugin,
    DetectorPlotPlugin,
    DetectorViewPlugin,
)
from acconeer.exptool.app.new.plugin import Plugin


class DistanceDetectorBackendPlugin(DetectorBackendPlugin):
    pass


class DistanceDetectorPlotPlugin(DetectorPlotPlugin):
    pass


class DistanceDetectorViewPlugin(DetectorViewPlugin):
    pass


DISTANCE_DETECTOR_PLUGIN = Plugin(
    key="distance_detector",
    backend_plugin=DistanceDetectorBackendPlugin,  # type: ignore[misc]
    plot_plugin=DistanceDetectorPlotPlugin,  # type: ignore[misc]
    view_plugin=DistanceDetectorViewPlugin,  # type: ignore[misc]
)
