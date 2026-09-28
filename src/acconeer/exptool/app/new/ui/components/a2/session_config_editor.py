# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a2
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.app.new.ui.components.attrs_config_editor import AttrsConfigEditor
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.components.json_save_load_buttons.buttons import (
    create_json_save_load_buttons,
)
from acconeer.exptool.app.new.ui.components.overlay import Overlay
from acconeer.exptool.app.new.ui.components.pidgets import pidgets
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping

from .sensor_config_editor import SensorConfigEditor


_PIDGET_MAPPING: PidgetFactoryMapping = {
    "update_rate": pidgets.OptionalFloatPidgetFactory(
        name_label_text="Update rate:",
        name_label_tooltip=get_attribute_docstring(a2.SessionConfig, "update_rate"),
        decimals=2,
        limits=(0.01, None),
    ),
}


class _SessionConfigParametersEditor(AttrsConfigEditor[a2.SessionConfig]):
    """This is a "partial editor" that only modifies some fields."""

    def __init__(self, save_load_buttons: bool, min_top_padding: int = 0) -> None:
        super().__init__(
            title="Session parameters",
            factory_mapping=_PIDGET_MAPPING,
            config_type=a2.SessionConfig,
            save_load_buttons=save_load_buttons,
            min_top_padding=min_top_padding,
        )


class SessionConfigEditor(DataEditor[a2.SessionConfig | None]):
    def __init__(self, save_load_buttons: bool = True, single_subsweep: bool = False) -> None:
        super().__init__()

        if save_load_buttons:
            overlay = (
                create_json_save_load_buttons(
                    self,
                    a2.SessionConfig.to_json,
                    a2.SessionConfig.from_json,
                ),
                Overlay.positioner_top_right,
            )
        else:
            overlay = None

        self._session_param_editor = _SessionConfigParametersEditor(
            save_load_buttons=False,
            min_top_padding=0 if not overlay else overlay[0].sizeHint().height() // 2,
        )
        self._session_param_editor.sig_update.connect(self._emit_current_data)

        self._sensor_config_editor = SensorConfigEditor(
            save_load_buttons=False, single_subsweep=single_subsweep
        )
        self._sensor_config_editor.sig_update.connect(self._emit_current_data)

        editors_wrapper = QWidget(self)
        editors_wrapper_layout = QVBoxLayout()
        editors_wrapper.setLayout(editors_wrapper_layout)
        editors_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        editors_wrapper_layout.addWidget(self._session_param_editor)
        editors_wrapper_layout.addWidget(self._sensor_config_editor)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(Overlay(editors_wrapper, [] if overlay is None else [overlay]))
        self.setLayout(layout)

    def _emit_current_data(self) -> None:
        self.sig_update.emit(self.get_data())

    def get_data(self) -> a2.SessionConfig | None:
        sensor_config = self._sensor_config_editor.get_data()
        partial_session_config = self._session_param_editor.get_data()

        if sensor_config is None or partial_session_config is None:
            return None
        else:
            return a2.SessionConfig(
                sensor_configs=[sensor_config],
                update_rate=partial_session_config.update_rate,
            )

    def set_data(self, data: a2.SessionConfig | None) -> None:
        self.setDisabled(data is None)

        if data is None:
            return

        if len(data.sensor_configs) > 1:
            msg = "Cannot handle more than 1 SensorConfig at the moment."
            raise NotImplementedError(msg)

        self._session_param_editor.set_data(data)
        self._sensor_config_editor.set_data(data.sensor_configs[0])

    @property
    def is_ready(self) -> bool:
        return self._session_param_editor.is_ready and self._sensor_config_editor.is_ready

    def handle_validation_results(self, results: list[ValidationResult]) -> list[ValidationResult]:
        not_handled = self._session_param_editor.handle_validation_results(results)
        not_handled = self._sensor_config_editor.handle_validation_results(not_handled)
        return not_handled
