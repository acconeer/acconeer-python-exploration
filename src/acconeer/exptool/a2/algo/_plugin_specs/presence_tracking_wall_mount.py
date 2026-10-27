# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto

from acconeer.exptool.app.new import PluginFamily, PluginGeneration, PluginPresetBase
from acconeer.exptool.app.new.pluginbase import BundledPluginSpec


class PluginPresetId(Enum):
    DEFAULT = auto()


PRESENCE_TRACKING_WALL_MOUNT_PLUGIN = BundledPluginSpec(
    generation=PluginGeneration.A2,
    key="presence_tracking_wall_mount",
    title="Presence Tracking Wall Mount",
    description="Count and track people.",
    family=PluginFamily.REF_APP,
    docs_link="https://docs.acconeer.com/en/latest/applications/a212/presence_tracking_wall_mount.html",
    presets=[
        PluginPresetBase(name="Default", preset_id=PluginPresetId.DEFAULT),
    ],
    default_preset_id=PluginPresetId.DEFAULT,
)
