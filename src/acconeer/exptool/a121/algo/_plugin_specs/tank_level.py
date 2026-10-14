# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Callable

from acconeer.exptool.app.new import (
    AppModel,
    Message,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
)


if TYPE_CHECKING:
    from acconeer.exptool.a121.algo.tank_level._plugin import BackendPlugin, PlotPlugin, ViewPlugin


class PluginPresetId(Enum):
    SMALL = auto()
    MEDIUM = auto()
    LARGE = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.tank_level._plugin import BackendPlugin

        return BackendPlugin(callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.tank_level._plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.tank_level._plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


TANK_LEVEL_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="tank_level",
    title="Tank level",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/tank_level.html",
    description="Measure liquid levels in tanks",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(name="Small", preset_id=PluginPresetId.SMALL),
        PluginPresetBase(name="Medium", preset_id=PluginPresetId.MEDIUM),
        PluginPresetBase(name="Large", preset_id=PluginPresetId.LARGE),
    ],
    default_preset_id=PluginPresetId.SMALL,
)
