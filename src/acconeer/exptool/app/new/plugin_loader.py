from __future__ import annotations

from .plugin import Plugin


def load_default_plugins() -> list[Plugin]:
    from acconeer.exptool.a121.algo.distance._plugins._detector import DISTANCE_DETECTOR_PLUGIN

    return [
        DISTANCE_DETECTOR_PLUGIN,
    ]
