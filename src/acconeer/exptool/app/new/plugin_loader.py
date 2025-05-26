# Copyright (c) Acconeer AB, 2022-2025
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
    from acconeer.exptool.a121.algo.bilateration._plugin import BILATERATION_PLUGIN
    from acconeer.exptool.a121.algo.breathing._ref_app_plugin import BREATHING_PLUGIN
    from acconeer.exptool.a121.algo.cargo._ex_app_plugin import CARGO_PLUGIN
    from acconeer.exptool.a121.algo.distance._detector_plugin import DISTANCE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo.hand_motion._example_app_plugin import HAND_MOTION_PLUGIN
    from acconeer.exptool.a121.algo.obstacle._detector_plugin import OBSTACLE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo.parking._ref_app_plugin import PARKING_PLUGIN
    from acconeer.exptool.a121.algo.phase_tracking._plugin import PHASE_TRACKING_PLUGIN
    from acconeer.exptool.a121.algo.presence._detector_plugin import PRESENCE_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo.smart_presence._ref_app_plugin import SMART_PRESENCE_PLUGIN
    from acconeer.exptool.a121.algo.sparse_iq._plugin import SPARSE_IQ_PLUGIN
    from acconeer.exptool.a121.algo.speed._detector_plugin import SPEED_DETECTOR_PLUGIN
    from acconeer.exptool.a121.algo.surface_velocity._example_app_plugin import (
        SURFACE_VELOCITY_PLUGIN,
    )
    from acconeer.exptool.a121.algo.tank_level._plugin import TANK_LEVEL_PLUGIN
    from acconeer.exptool.a121.algo.touchless_button._plugin import TOUCHLESS_BUTTON_PLUGIN
    from acconeer.exptool.a121.algo.vibration._example_app_plugin import VIBRATION_PLUGIN
    from acconeer.exptool.a121.algo.waste_level._plugin import WASTE_LEVEL_PLUGIN

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
    ]


def load_plugins() -> list[PluginSpec]:
    return load_default_plugins() + get_registered_plugins()
