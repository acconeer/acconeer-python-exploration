# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any, Callable, Optional

import attrs
from typing_extensions import Literal

from acconeer.exptool._artifact_repository import module_bundle_packages
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.backend import BackendPlugin, Message
from acconeer.exptool.app.new.ui import DataEditor

from .plot_plugin_base import PlotPluginBase
from .plugin_spec_base import PluginSpecBase
from .view_plugin_base import ViewPluginBase


@attrs.frozen(kw_only=True)
class BundledPluginSpec(PluginSpecBase):
    """Lists a plugin whose implementation ships in the module bundle.

    A package in the bundle provides it in its ``plugin_specs`` module as
    ``PLUGIN_SPECS``, a mapping from plugin key to a ``PluginSpecBase``
    subclass. A submodule, so that importing the package loads no plugin. That class is created with
    the fields of this spec, so they are kept in one place.
    """

    requires_module_bundle_artifact: bool = attrs.field(default=True, init=False)

    def _bundled(self) -> PluginSpecBase:
        for package in module_bundle_packages():
            module = f"{package}.plugin_specs"
            if importlib.util.find_spec(module) is None:
                continue
            spec_classes = importlib.import_module(module).PLUGIN_SPECS
            if self.key in spec_classes:
                fields = {
                    f.name: getattr(self, f.name) for f in attrs.fields(PluginSpecBase) if f.init
                }
                return spec_classes[self.key](**fields)  # type: ignore[no-any-return]

        msg = (
            f"The module bundle has no plugin {self.key!r}, so it is likely older than "
            'the Exploration Tool. Click "installed" next to the plugin to delete the '
            "bundle, restart the Exploration Tool and select the plugin again to download "
            "the latest bundle."
        )
        raise ValueError(msg)

    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin[Any]:
        return self._bundled().create_backend_plugin(callback, key)

    def create_view_plugin(self, app_model: AppModel) -> ViewPluginBase:
        return self._bundled().create_view_plugin(app_model)

    def create_plot_plugin(self, app_model: AppModel) -> PlotPluginBase:
        return self._bundled().create_plot_plugin(app_model)

    # Instance methods, unlike the base's class methods, since the key picks the bundled spec
    def replay_dialog_create_config_editor(self) -> Optional[DataEditor[Any]]:  # type: ignore[override]
        return self._bundled().replay_dialog_create_config_editor()

    def replay_dialog_get_config(  # type: ignore[override]
        self, file: Path
    ) -> Optional[tuple[Literal["default", "loaded"], Any, Any]]:
        return self._bundled().replay_dialog_get_config(file)
