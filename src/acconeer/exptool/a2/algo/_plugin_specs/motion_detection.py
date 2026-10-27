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
    from acconeer.exptool.a2.algo.motion_detection.plugin import (
        BackendPlugin,
        PlotPlugin,
        ReplayDialogConfig,
        ReplayDialogConfigEditor,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    SITTING = auto()
    WALKING = auto()


class PluginSpec(PluginSpecBase):
    @classmethod
    def replay_dialog_get_config(
        cls, path: Path
    ) -> tuple[Literal["default", "loaded"], ReplayDialogConfig, a2.SessionConfig]:
        from acconeer.exptool.a2.algo.motion_detection.plugin import _replay_dialog_get_config

        return _replay_dialog_get_config(path)

    @classmethod
    def replay_dialog_create_config_editor(cls) -> ReplayDialogConfigEditor:
        from acconeer.exptool.a2.algo.motion_detection.plugin import ReplayDialogConfigEditor

        return ReplayDialogConfigEditor()

    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a2.algo.motion_detection.plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a2.algo.motion_detection.plugin import ViewPlugin

        return ViewPlugin(app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a2.algo.motion_detection.plugin import PlotPlugin

        return PlotPlugin(app_model)


MOTION_DETECTION_PLUGIN = PluginSpec(
    generation=PluginGeneration.A2,
    key="motion_detection",
    title="Motion Detection",
    description="Locate moving objects in 3D.",
    family=PluginFamily.EXAMPLE_APP,
    docs_link="https://docs.acconeer.com/en/latest/applications/a212/motion_detection.html",
    presets=[
        PluginPresetBase(name="Walking detection", preset_id=PluginPresetId.WALKING),
        PluginPresetBase(name="Sitting detection", preset_id=PluginPresetId.SITTING),
    ],
    default_preset_id=PluginPresetId.WALKING,
)
