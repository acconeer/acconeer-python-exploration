# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Callable, Literal

from acconeer.exptool.app.new import (
    AppModel,
    Message,
    PluginFamily,
    PluginGeneration,
    PluginPresetBase,
    PluginSpecBase,
)


if TYPE_CHECKING:
    from pathlib import Path

    from acconeer.exptool import a2
    from acconeer.exptool.a2.algo.heatmap.backend_plugin_common import BackendPlugin
    from acconeer.exptool.a2.algo.heatmap.capon.config import HeatmapConfig
    from acconeer.exptool.a2.algo.heatmap.capon.plugin import ViewPlugin
    from acconeer.exptool.a2.algo.heatmap.plot_config_common import HeatmapPlotConfig
    from acconeer.exptool.a2.algo.heatmap.plot_plugin_common import PlotPlugin
    from acconeer.exptool.app.new.ui import AttrsConfigEditor


class PluginPresetId(Enum):
    DEFAULT = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin[HeatmapConfig, HeatmapPlotConfig]:
        from acconeer.exptool.a2.algo.heatmap.capon.plugin import _create_backend_plugin

        return _create_backend_plugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a2.algo.heatmap.capon.plugin import ViewPlugin

        return ViewPlugin(app_model)

    def create_plot_plugin(
        self, app_model: AppModel
    ) -> PlotPlugin[HeatmapConfig, HeatmapPlotConfig]:
        from acconeer.exptool.a2.algo.heatmap.plot_plugin_common import PlotPlugin

        return PlotPlugin(app_model)

    @classmethod
    def replay_dialog_create_config_editor(cls) -> AttrsConfigEditor[HeatmapConfig]:
        from acconeer.exptool.a2.algo.heatmap.capon.plugin import _create_config_editor

        return _create_config_editor()

    @classmethod
    def replay_dialog_get_config(
        cls, path: Path
    ) -> tuple[Literal["default", "loaded"], HeatmapConfig, a2.SessionConfig]:
        from acconeer.exptool.a2.algo.heatmap.capon.plugin import _replay_dialog_get_config

        return _replay_dialog_get_config(path)


CAPON_HEATMAP_PLUGIN = PluginSpec(
    generation=PluginGeneration.A2,
    key="capon_heatmap",
    title="Capon Heatmap",
    description="Capon beamformed heatmap.",
    family=PluginFamily.PROCESSORS,
    docs_link="https://docs.acconeer.com/en/latest/applications/a212/heatmap/capon.html",
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
