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
    from acconeer.exptool.a121.algo.obstacle._detector_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    DEFAULT = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.obstacle._detector_plugin import BackendPlugin

        return BackendPlugin(callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.obstacle._detector_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.obstacle._detector_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


OBSTACLE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="obstacle_detector",
    title="Obstacle detection",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/obstacle_detection.html",
    description="Measure distance and angle to objects from a moving platform.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
