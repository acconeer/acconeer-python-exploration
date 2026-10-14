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
    from acconeer.exptool.a121.algo.vibration._example_app_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    LOW_FREQ = auto()
    HIGH_FREQ = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.vibration._example_app_plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.vibration._example_app_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.vibration._example_app_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


VIBRATION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="vibration",
    title="Vibration measurement",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/vibration.html",
    description="Quantify the frequency content of vibrating object.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Low frequency", preset_id=PluginPresetId.LOW_FREQ),
        PluginPresetBase(name="High frequency", preset_id=PluginPresetId.HIGH_FREQ),
    ],
    default_preset_id=PluginPresetId.LOW_FREQ,
)
