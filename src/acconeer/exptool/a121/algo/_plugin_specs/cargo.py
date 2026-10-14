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
    from acconeer.exptool.a121.algo.cargo._ex_app_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    CONTAINER_10_FT = auto()
    CONTAINER_20_FT = auto()
    CONTAINER_40_FT = auto()
    NO_LENS = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.cargo._ex_app_plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.cargo._ex_app_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.cargo._ex_app_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


CARGO_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="cargo",
    title="Cargo",
    docs_link="https://docs.acconeer.com/en/latest/example_apps/a121/cargo.html",
    description="Detects utilization level and presence in container.",
    family=PluginFamily.EXAMPLE_APP,
    presets=[
        PluginPresetBase(
            name="10 feet (3 m)",
            description="Container 10 feet (3 m)",
            preset_id=PluginPresetId.CONTAINER_10_FT,
        ),
        PluginPresetBase(
            name="20 feet (6 m)",
            description="Container 20 feet (6 m)",
            preset_id=PluginPresetId.CONTAINER_20_FT,
        ),
        PluginPresetBase(
            name="40 feet (12 m)",
            description="Container 40 feet (12 m)",
            preset_id=PluginPresetId.CONTAINER_40_FT,
        ),
        PluginPresetBase(
            name="No lens",
            description="No lens configuration",
            preset_id=PluginPresetId.NO_LENS,
        ),
    ],
    default_preset_id=PluginPresetId.NO_LENS,
)
