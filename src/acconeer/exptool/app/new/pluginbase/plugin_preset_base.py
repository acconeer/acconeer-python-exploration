# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from enum import Enum
from typing import Optional

import attrs

from acconeer.exptool.app.new.app_model import PluginPresetSpec


@attrs.frozen(kw_only=True)
class PluginPresetBase(PluginPresetSpec):
    name: str = attrs.field()
    description: Optional[str] = attrs.field(default=None)
    preset_id: Enum = attrs.field(default=None)
