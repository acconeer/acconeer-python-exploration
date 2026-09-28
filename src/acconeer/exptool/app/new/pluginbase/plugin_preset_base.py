# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from enum import Enum

import attrs

from acconeer.exptool.app.new.app_model import PluginPresetSpec


@attrs.frozen(kw_only=True)
class PluginPresetBase(PluginPresetSpec):
    name: str = attrs.field()
    description: str | None = attrs.field(default=None)
    preset_id: Enum = attrs.field(default=None)
