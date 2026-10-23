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
    from acconeer.exptool.a2.algo.heatmap.backend_plugin_common import BackendPlugin
    from acconeer.exptool.a2.algo.heatmap.coherent.config import HeatmapConfig
    from acconeer.exptool.a2.algo.heatmap.coherent.plot_config import (
        CoherentHeatmapPlotConfig,
    )
    from acconeer.exptool.a2.algo.heatmap.coherent.plugin import PlotPlugin, ViewPlugin


class PluginPresetId(Enum):
    DEFAULT = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin[HeatmapConfig, CoherentHeatmapPlotConfig]:
        from acconeer.exptool.a2.algo.heatmap.coherent.plugin import _create_backend_plugin

        return _create_backend_plugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a2.algo.heatmap.coherent.plugin import ViewPlugin

        return ViewPlugin(app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a2.algo.heatmap.coherent.plugin import PlotPlugin

        return PlotPlugin(app_model)


COHERENT_HEATMAP_PLUGIN = PluginSpec(
    generation=PluginGeneration.A2,
    key="coherent_heatmap",
    title="Coherent Heatmap",
    description="Coherent heatmap.",
    family=PluginFamily.PROCESSORS,
    docs_link="https://docs.acconeer.com/en/latest/applications/a212/heatmap/coherent.html",
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
