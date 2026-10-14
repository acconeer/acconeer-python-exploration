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
    from acconeer.exptool.a121.algo.breathing._ref_app_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    SITTING = auto()
    INFANT = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.breathing._ref_app_plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.breathing._ref_app_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.breathing._ref_app_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


BREATHING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="breathing",
    title="Breathing",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/breathing.html",
    description="Detect breathing rate.",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(
            name="Sitting",
            description="Sitting",
            preset_id=PluginPresetId.SITTING,
        ),
        PluginPresetBase(
            name="Infant",
            description="Infant",
            preset_id=PluginPresetId.INFANT,
        ),
    ],
    default_preset_id=PluginPresetId.SITTING,
)
