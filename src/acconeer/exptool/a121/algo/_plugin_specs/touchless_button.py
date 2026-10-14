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
    from acconeer.exptool.a121.algo.touchless_button._plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    CLOSE_RANGE = auto()
    FAR_RANGE = auto()
    CLOSE_AND_FAR_RANGE = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.touchless_button._plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.touchless_button._plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.touchless_button._plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


TOUCHLESS_BUTTON_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="touchless_button",
    title="Touchless button",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/touchless_button.html",
    description="Detect tap/wave motion and register as button press.",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(
            name="Close range",
            description="Close range",
            preset_id=PluginPresetId.CLOSE_RANGE,
        ),
        PluginPresetBase(
            name="Far range",
            description="Far range",
            preset_id=PluginPresetId.FAR_RANGE,
        ),
        PluginPresetBase(
            name="Close and far range",
            description="Close and far range",
            preset_id=PluginPresetId.CLOSE_AND_FAR_RANGE,
        ),
    ],
    default_preset_id=PluginPresetId.CLOSE_RANGE,
)
