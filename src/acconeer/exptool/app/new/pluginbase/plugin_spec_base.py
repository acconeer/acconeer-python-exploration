# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
from enum import Enum
from typing import Any, Callable, List, Optional

import attrs

from acconeer.exptool.app.new._enums import PluginFamily, PluginGeneration
from acconeer.exptool.app.new.app_model import AppModel, PluginPresetSpec, PluginSpec
from acconeer.exptool.app.new.backend import BackendPlugin, Message

from .plot_plugin_base import PlotPluginBase
from .view_plugin_base import ViewPluginBase


@attrs.frozen(kw_only=True)
class PluginSpecBase(abc.ABC, PluginSpec):
    generation: PluginGeneration = attrs.field()
    key: str = attrs.field()
    title: str = attrs.field()
    docs_link: Optional[str] = attrs.field(default=None)
    description: Optional[str] = attrs.field(default=None)
    family: PluginFamily = attrs.field()
    presets: List[PluginPresetSpec] = attrs.field()
    default_preset_id: Enum = attrs.field()

    @abc.abstractmethod
    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin[Any]:
        pass

    @abc.abstractmethod
    def create_view_plugin(self, app_model: AppModel) -> ViewPluginBase:
        pass

    @abc.abstractmethod
    def create_plot_plugin(self, app_model: AppModel) -> PlotPluginBase:
        pass
