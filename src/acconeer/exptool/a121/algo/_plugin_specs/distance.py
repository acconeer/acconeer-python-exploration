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
    from acconeer.exptool.a121.algo.distance._detector_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    BALANCED = auto()
    HIGH_ACCURACY = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.distance._detector_plugin import BackendPlugin

        return BackendPlugin(callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.distance._detector_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.distance._detector_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


DISTANCE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="distance_detector",
    title="Distance detector",
    docs_link="https://docs.acconeer.com/en/latest/detectors/a121/distance_detector.html",
    description="Easily measure distance to objects.",
    family=PluginFamily.DETECTOR,
    presets=[
        PluginPresetBase(name="Balanced", preset_id=PluginPresetId.BALANCED),
        PluginPresetBase(name="High accuracy", preset_id=PluginPresetId.HIGH_ACCURACY),
    ],
    default_preset_id=PluginPresetId.BALANCED,
)
