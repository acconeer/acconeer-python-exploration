# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from .app_model import PluginSpec


def load_default_plugins() -> list[PluginSpec]:
    from acconeer.exptool.a121.algo.bilateration._plugin import BILATERATION_PLUGIN
    from acconeer.exptool.a121.algo.distance._detector_plugin import DISTANCE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo.phase_tracking._plugin import PHASE_TRACKING_PLUGIN
    from acconeer.exptool.a121.algo.presence._detector_plugin import PRESENCE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo.sparse_iq._plugin import SPARSE_IQ_PLUGIN
    from acconeer.exptool.a121.algo.touchless_button._plugin import TOUCHLESS_BUTTON_PLUGIN
    from acconeer.exptool.a121.algo.vibration._plugin import VIBRATION_PLUGIN

    return [
        SPARSE_IQ_PLUGIN,
        DISTANCE_DETECTOR_PLUGIN,
        PHASE_TRACKING_PLUGIN,
        PRESENCE_DETECTOR_PLUGIN,
        TOUCHLESS_BUTTON_PLUGIN,
        VIBRATION_PLUGIN,
        BILATERATION_PLUGIN,
    ]
