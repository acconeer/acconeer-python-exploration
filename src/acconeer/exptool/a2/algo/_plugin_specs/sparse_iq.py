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
    from acconeer.exptool.a2.algo.sparse_iq.plugin import BackendPlugin, PlotPlugin, ViewPlugin


class PluginPresetId(Enum):
    DEFAULT = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a2.algo.sparse_iq.plugin import BackendPlugin

        return BackendPlugin(callback, self.generation, key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a2.algo.sparse_iq.plugin import ViewPlugin

        return ViewPlugin(app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a2.algo.sparse_iq.plugin import PlotPlugin

        return PlotPlugin(app_model)


SPARSE_IQ_PLUGIN = PluginSpec(
    generation=PluginGeneration.A2,
    key="sparse_iq",
    title="Sparse IQ",
    description="Basic usage of the sparse IQ service.",
    family=PluginFamily.SERVICE,
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
