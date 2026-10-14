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
    from acconeer.exptool.a121.algo.waste_level._plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    PLASTIC_WASTE_BIN = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.waste_level._plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.waste_level._plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.waste_level._plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


WASTE_LEVEL_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="waste_level",
    title="Waste level",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/waste_level.html",
    description="Detect waste level in a bin.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(
            name="Plastic waste bin",
            description="Settings for measuring waste level in a plastic waste bin (240 liter)",
            preset_id=PluginPresetId.PLASTIC_WASTE_BIN,
        ),
    ],
    default_preset_id=PluginPresetId.PLASTIC_WASTE_BIN,
)
