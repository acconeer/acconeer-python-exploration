# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import typing_extensions as te

from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new._enums import ConnectionState, PluginGeneration, PluginState
from acconeer.exptool.app.new.app_model import AppModel


class PolicyFunction(te.Protocol):
    def __call__(self, app_model: AppModel, *, extra_condition: bool = True) -> bool: ...


def start_button_enabled(app_model: AppModel, *, extra_condition: bool = True) -> bool:
    return (
        app_model.plugin_state == PluginState.LOADED_IDLE
        and app_model.connection_state == ConnectionState.CONNECTED
        and app_model.plugin_generation == PluginGeneration.A121
        and bool(app_model.connected_sensors)
        and app_model.backend_plugin_state is not None
        and getattr(app_model.backend_plugin_state, "ready", True)
        and extra_condition
    )


def stop_button_enabled(app_model: AppModel, *, extra_condition: bool = True) -> bool:
    return app_model.plugin_state == PluginState.LOADED_BUSY and extra_condition


def config_editor_enabled(app_model: AppModel, *, extra_condition: bool = True) -> bool:
    return app_model.plugin_state == PluginState.LOADED_IDLE and extra_condition


def apply_enabled_policy(
    policy_func: PolicyFunction,
    app_model: AppModel,
    widgets: list[QWidget],
    *,
    extra_condition: bool = True,
) -> None:
    for widget in widgets:
        widget.setEnabled(policy_func(app_model, extra_condition=extra_condition))
