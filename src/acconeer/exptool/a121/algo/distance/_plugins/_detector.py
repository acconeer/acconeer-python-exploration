from __future__ import annotations

from acconeer.exptool.a121.algo._plugins import DetectorBackendPlugin
from acconeer.exptool.app.new.plugin import Plugin


class DistanceDetectorBackendPlugin(DetectorBackendPlugin):
    pass


DISTANCE_DETECTOR_PLUGIN = Plugin(
    key="distance_detector",
    backend_plugin=DistanceDetectorBackendPlugin,
)
