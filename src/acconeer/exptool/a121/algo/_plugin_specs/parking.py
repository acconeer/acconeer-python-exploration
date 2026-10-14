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
    from acconeer.exptool.a121.algo.parking._ref_app_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    GROUND = auto()
    POLE = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.parking._ref_app_plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.parking._ref_app_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.parking._ref_app_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


PARKING_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="parking",
    title="Parking",
    docs_link="https://docs.acconeer.com/en/latest/ref_apps/a121/parking.html",
    description="Detect parked cars.",
    family=PluginFamily.REF_APP,
    presets=[
        PluginPresetBase(
            name="Ground",
            description="Ground mounted",
            preset_id=PluginPresetId.GROUND,
        ),
        PluginPresetBase(
            name="Pole",
            description="Pole mounted",
            preset_id=PluginPresetId.POLE,
        ),
    ],
    default_preset_id=PluginPresetId.GROUND,
)
