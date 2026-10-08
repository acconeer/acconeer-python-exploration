# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import abc
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional

import attrs
from typing_extensions import Literal

from acconeer.exptool.app.new._enums import PluginFamily, PluginGeneration
from acconeer.exptool.app.new.app_model import AppModel, PluginPresetSpec, PluginSpec
from acconeer.exptool.app.new.backend import BackendPlugin, Message
from acconeer.exptool.app.new.ui import DataEditor

from .plot_plugin_base import PlotPluginBase
from .view_plugin_base import ViewPluginBase


_UniqueConfigAlias = Any
_ValidatingConfigAlias = Any


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
    requires_module_bundle_artifact: bool = attrs.field(default=False)

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

    @classmethod
    def replay_dialog_create_config_editor(cls) -> Optional[DataEditor[Any]]:
        """Opt-in factory for the unique config editor used in the plugin.

        Should only be used to support replay dialogs in its current form.
        """
        return None

    @classmethod
    def replay_dialog_get_config(
        cls, file: Path
    ) -> Optional[
        tuple[
            Literal["default", "loaded"],
            _UniqueConfigAlias,
            _ValidatingConfigAlias,
        ]
    ]:
        """Opt-in function to extract the ...

        - Unique config used in the plugin (and whether its default or actually loaded)
        - A config to validate against.

        The config object will be edited with an editor returned from
        ``replay_dialog_create_config_editor``.

        Should only be used to support replay dialogs in its current form.
        """
        return None
