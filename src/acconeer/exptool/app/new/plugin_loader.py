# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import importlib
import logging
import typing as t

import attrs
import typing_extensions as te

from ._enums import PluginFamily
from .app_model import PluginSpec


_REGISTERED_PLUGINS: t.List[PluginSpec] = []
_LOG = logging.getLogger(__name__)


def register_plugin(plugin: PluginSpec) -> None:
    """Registers a plugin, to be used in the Exploration Tool App.

    :param plugin: A plugin
    """
    try:
        plugin = attrs.evolve(plugin, family=PluginFamily.EXTERNAL_PLUGIN)  # type: ignore[misc]
    except Exception:
        _LOG.error(f"Plugin {type(plugin).__name__!r} needs to be an instance of PluginSpecBase")
    finally:
        _REGISTERED_PLUGINS.append(plugin)


def get_registered_plugins() -> list[PluginSpec]:
    return _REGISTERED_PLUGINS


@te.runtime_checkable
class ThirdPartyPluginModule(te.Protocol):
    def register(self) -> None:
        # "self" refers to the module, i.e. is of type "ModuleType"
        ...


def import_and_register_plugin_module(module_name: str) -> None:
    imported_module = importlib.import_module(name=module_name)

    if not isinstance(imported_module, ThirdPartyPluginModule):
        msg = f"Module specified by {module_name!r} does not have a 'register' function."
        raise ValueError(msg)

    try:
        imported_module.register()
    except TypeError:
        raise TypeError(
            f"Function 'register' in {module_name!r} has the wrong signature. "
            + "'register' should have no parameters (should look like this: 'def register(): ...')"
        ) from None


def load_default_plugins() -> list[PluginSpec]:
    from acconeer.exptool.a2.algo._plugin_specs.capon_heatmap import (
        CAPON_HEATMAP_PLUGIN as CAPON_HEATMAP,
    )
    from acconeer.exptool.a2.algo._plugin_specs.conventional_heatmap import (
        CONVENTIONAL_HEATMAP_PLUGIN as CONVENTIONAL_HEATMAP,
    )
    from acconeer.exptool.a2.algo._plugin_specs.robust_capon_heatmap import (
        ROBUST_CAPON_HEATMAP_PLUGIN as ROBUST_CAPON_HEATMAP,
    )
    from acconeer.exptool.a2.algo._plugin_specs.sparse_iq import (
        SPARSE_IQ_PLUGIN as SPARSE_IQ_PLUGIN_A2,
    )
    from acconeer.exptool.a121.algo._plugin_specs.bilateration import BILATERATION_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.breathing import BREATHING_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.cargo import CARGO_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.distance import DISTANCE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.hand_motion import HAND_MOTION_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.obstacle import OBSTACLE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.parking import PARKING_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.phase_tracking import PHASE_TRACKING_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.presence import PRESENCE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.smart_presence import SMART_PRESENCE_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.sparse_iq import SPARSE_IQ_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.speed import SPEED_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.surface_velocity import (
        SURFACE_VELOCITY_PLUGIN,
    )
    from acconeer.exptool.a121.algo._plugin_specs.tank_level import TANK_LEVEL_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.touchless_button import TOUCHLESS_BUTTON_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.vibration import VIBRATION_PLUGIN
    from acconeer.exptool.a121.algo._plugin_specs.waste_level import WASTE_LEVEL_PLUGIN

    # Please keep in lexicographical order
    return [
        BILATERATION_PLUGIN,
        BREATHING_PLUGIN,
        CARGO_PLUGIN,
        DISTANCE_DETECTOR_PLUGIN,
        HAND_MOTION_PLUGIN,
        OBSTACLE_DETECTOR_PLUGIN,
        PARKING_PLUGIN,
        PHASE_TRACKING_PLUGIN,
        PRESENCE_DETECTOR_PLUGIN,
        SMART_PRESENCE_PLUGIN,
        SPARSE_IQ_PLUGIN,
        SURFACE_VELOCITY_PLUGIN,
        TANK_LEVEL_PLUGIN,
        TOUCHLESS_BUTTON_PLUGIN,
        VIBRATION_PLUGIN,
        SPEED_DETECTOR_PLUGIN,
        WASTE_LEVEL_PLUGIN,
        # A2 plugins
        SPARSE_IQ_PLUGIN_A2,
        CAPON_HEATMAP,
        ROBUST_CAPON_HEATMAP,
        CONVENTIONAL_HEATMAP,
    ]


def load_plugins() -> list[PluginSpec]:
    return load_default_plugins() + get_registered_plugins()
