# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .data_editor import DataEditor
from .json_save_load_buttons import create_json_save_load_buttons
from .sensor_config_editor import SensorConfigEditor
from .utils import GroupBox


log = logging.getLogger(__name__)


def session_or_sensor_config_json_to_session_config(json_str: str) -> a121.SessionConfig:
    try:
        return a121.SessionConfig.from_json(json_str)
    except KeyError:
        return a121.SessionConfig(a121.SensorConfig.from_json(json_str))


class SessionConfigEditor(DataEditor[Optional[a121.SessionConfig]]):
    _session_config: Optional[a121.SessionConfig]
    _server_info: Optional[a121.ServerInfo]
    _sensor_id_pidget: pidgets.SensorIdPidget

    _update_rate_erroneous: bool

    sig_update = Signal(object)

    SPACING = 15

    def __init__(
        self, supports_multiple_subsweeps: bool = False, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)

        self._server_info = None

        self._session_config = None
        self._update_rate_erroneous = False

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.session_group_box = GroupBox.vertical(
            "Session parameters",
            create_json_save_load_buttons(
                self,
                encoder=a121.SessionConfig.to_json,
                decoder=session_or_sensor_config_json_to_session_config,
            ),
            parent=self,
        )
        self.session_group_box.layout().setSpacing(self.SPACING)
        self.layout().addWidget(self.session_group_box)

        self._sensor_id_pidget = pidgets.SensorIdPidgetFactory(items=[]).create(self)
        self._sensor_id_pidget.sig_update.connect(self._update_sole_sensor_id)
        self.session_group_box.layout().addWidget(self._sensor_id_pidget)

        self._update_rate_pidget = pidgets.OptionalFloatPidgetFactory(
            name_label_text="Update rate:",
            name_label_tooltip=(
                "Set an update rate limit on the server.\n"
                "If 'Limit' is unchecked, the server will run as fast as possible."
            ),
            limits=(0.1, 1e4),
            decimals=1,
            init_set_value=10.0,
            placeholder_text="- Hz",
            suffix="Hz",
            checkbox_label_text="Limit",
        ).create(self)
        self._update_rate_pidget.sig_update.connect(self._update_update_rate)
        self.session_group_box.layout().addWidget(self._update_rate_pidget)

        self._sensor_config_editor = SensorConfigEditor(supports_multiple_subsweeps, parent=self)
        self._sensor_config_editor.sig_update.connect(self._update_sole_sensor_config)
        self.layout().addWidget(self._sensor_config_editor)

    def set_selectable_sensors(self, sensor_list: list[int]) -> None:
        self._sensor_id_pidget.set_selectable_sensors(sensor_list)

    def set_read_only(self, read_only: bool) -> None:
        self._sensor_id_pidget.setEnabled(not read_only)
        self._update_rate_pidget.setEnabled(not read_only)
        self._sensor_config_editor.set_read_only(read_only)

    def set_data(self, session_config: Optional[a121.SessionConfig]) -> None:
        if self._session_config == session_config:
            return

        self._session_config = session_config
        self.setEnabled(session_config is not None)

        if self._session_config is None:
            log.debug("could not update ui as SessionConfig is None")
            return

        self._sensor_id_pidget.set_data(self._session_config.sensor_id)
        self._update_rate_pidget.set_data(self._session_config.update_rate)
        self._sensor_config_editor.set_data(self._session_config.sensor_config)

    def get_data(self) -> Optional[a121.SessionConfig]:
        return copy.deepcopy(self._session_config)

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        self._update_rate_pidget.set_note_text(None)
        self._sensor_id_pidget.set_note_text(None)

        unhandled_results: list[a121.ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        unhandled_results = self._sensor_config_editor.handle_validation_results(unhandled_results)

        return unhandled_results

    @property
    def is_ready(self) -> bool:
        return not self._update_rate_erroneous and self._sensor_config_editor.is_ready

    def _handle_validation_result(self, result: a121.ValidationResult) -> bool:
        if self._session_config is None:
            raise RuntimeError(
                "SessionConfigEditor's config is None while ValidationResults are being handled."
            )

        result_handled = False

        if result.aspect == "update_rate":
            self._update_rate_pidget.set_note_text(result.message, result.criticality)
            result_handled = True
        elif result.aspect == "sensor_id":
            self._sensor_id_pidget.set_note_text(result.message, result.criticality)
            result_handled = True

        return result_handled

    def _update_update_rate(self, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")

        config = copy.deepcopy(self._session_config)

        try:
            config.update_rate = value
        except Exception as e:
            self._update_rate_erroneous = True
            self._update_rate_pidget.set_note_text(e.args[0], Criticality.ERROR)

            # this emit needs to be done to signal that "is_ready" has changed.
            self.sig_update.emit(self.get_data())
        else:
            self._update_rate_erroneous = False

            self.set_data(config)
            self.sig_update.emit(config)

    def _update_sole_sensor_id(self, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")

        config = copy.deepcopy(self._session_config)

        try:
            config.sensor_id = value
        except Exception as e:
            self._sensor_id_pidget.set_note_text(e.args[0], Criticality.ERROR)

        self.set_data(config)
        self.sig_update.emit(config)

    def _update_sole_sensor_config(self, sensor_config: a121.SensorConfig) -> None:
        if self._session_config is None:
            raise RuntimeError

        config = a121.SessionConfig(
            {self._session_config.sensor_id: sensor_config},
            update_rate=self._session_config.update_rate,
            extended=self._session_config.extended,
        )
        self.set_data(config)
        self.sig_update.emit(config)
