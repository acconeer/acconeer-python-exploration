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
    from acconeer.exptool.a121.algo.presence._detector_plugin import (
        BackendPlugin,
        PlotPlugin,
        ViewPlugin,
    )


class PluginPresetId(Enum):
    SHORT_RANGE = auto()
    MEDIUM_RANGE = auto()
    LONG_RANGE = auto()
    LOW_POWER = auto()


class PluginSpec(PluginSpecBase):
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin:
        from acconeer.exptool.a121.algo.presence._detector_plugin import BackendPlugin

        return BackendPlugin(callback=callback, generation=self.generation, key=key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPlugin:
        from acconeer.exptool.a121.algo.presence._detector_plugin import ViewPlugin

        return ViewPlugin(app_model=app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPlugin:
        from acconeer.exptool.a121.algo.presence._detector_plugin import PlotPlugin

        return PlotPlugin(app_model=app_model)


PRESENCE_DETECTOR_PLUGIN = PluginSpec(
    generation=PluginGeneration.A121,
    key="presence_detector",
    title="Presence detector",
    docs_link="https://docs.acconeer.com/en/latest/detectors/a121/presence_detector.html",
    description="Detect human presence.",
    family=PluginFamily.DETECTOR,
    presets=[
        PluginPresetBase(
            name="Short range",
            description="Short range",
            preset_id=PluginPresetId.SHORT_RANGE,
        ),
        PluginPresetBase(
            name="Medium range",
            description="Medium range",
            preset_id=PluginPresetId.MEDIUM_RANGE,
        ),
        PluginPresetBase(
            name="Long range",
            description="Long range",
            preset_id=PluginPresetId.LONG_RANGE,
        ),
        PluginPresetBase(
            name="Low power, Wake up",
            description="Low power presence detection, which can be used as a trigger",
            preset_id=PluginPresetId.LOW_POWER,
        ),
    ],
    default_preset_id=PluginPresetId.MEDIUM_RANGE,
)
