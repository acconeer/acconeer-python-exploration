from __future__ import annotations

import logging
from functools import partial
from typing import Any, Mapping, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .sensor_config_editor import SensorConfigEditor
from .types import PidgetFactoryMapping
from .utils import VerticalGroupBox


log = logging.getLogger(__name__)


class SessionConfigEditor(QWidget):
    _session_config: Optional[a121.SessionConfig]
    _all_pidgets: list[pidgets.ParameterWidget]
    _server_info: Optional[a121.ServerInfo]

    sig_update = Signal(object)

    SPACING = 15

    SESSION_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "sensor_id": pidgets.UpdateableComboboxParameterWidgetFactory(
            name_label_text="Sensor:",
            items=[],
        ),
        "update_rate": pidgets.OptionalFloatParameterWidgetFactory(
            name_label_text="Update rate:",
            limits=(0.1, 1e4),
            decimals=1,
            init_set_value=10.0,
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._server_info = None

        self._session_config = None
        self._all_pidgets = []

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self._sensor_config_editor = SensorConfigEditor(self)

        self._sensor_config_editor.sig_update.connect(self._broadcast)

        # Session pidgets

        self.session_group_box = VerticalGroupBox("Session parameters", parent=self)
        self.session_group_box.layout().setSpacing(self.SPACING)
        self.layout().addWidget(self.session_group_box)

        self._session_config_pidgets: Mapping[str, pidgets.ParameterWidget] = {}
        for aspect, factory in self.SESSION_CONFIG_FACTORIES.items():
            pidget = factory.create(self.session_group_box)
            self.session_group_box.layout().addWidget(pidget)

            pidget.sig_parameter_changed.connect(
                partial(self._update_session_config_aspect, aspect)
            )

            self._all_pidgets.append(pidget)
            self._session_config_pidgets[aspect] = pidget

        self.layout().addWidget(self._sensor_config_editor)

    def set_data(self, session_config: Optional[a121.SessionConfig]) -> None:
        self._session_config = session_config
        if session_config is not None:
            self._sensor_config_editor.set_data(session_config.sensor_config)

    def sync(self) -> None:
        self._update_ui()
        self._sensor_config_editor.sync()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled and self._session_config is not None)

    def _broadcast(self) -> None:
        self.sig_update.emit(self._session_config)

    def _handle_validation_results(self, results: list[a121.ValidationResult]) -> None:
        if results == []:
            for pidget in self._all_pidgets:
                pidget.set_note_text("")
        else:
            for result in results:
                self._handle_validation_result(result)

    def _update_session_config_aspect(self, aspect: str, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")
        try:
            setattr(self._session_config, aspect, value)
        except Exception as e:
            self._session_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

        self._broadcast()

    def _handle_validation_result(self, result: a121.ValidationResult) -> None:
        if result.aspect is None or self._session_config is None:
            return

        if result.source is self._session_config:
            pidget_map = self._session_config_pidgets
        else:
            return

        pidget_map[result.aspect].set_note_text(result.message, result.criticality)

    def _update_ui(self) -> None:
        if self._session_config is None:
            log.debug("could not update ui as SessionConfig is None")
            return

        self._session_config_pidgets["update_rate"].set_parameter(self._session_config.update_rate)
        self._session_config_pidgets["sensor_id"].set_parameter(self._session_config.sensor_id)

    def update_available_sensor_list(self, server_info: Optional[a121.ServerInfo]) -> None:
        if self._server_info == server_info:
            return

        self._server_info = server_info
        if server_info is None:
            self._session_config_pidgets["sensor_id"].update_items([])
        else:
            self._session_config_pidgets["sensor_id"].update_items(
                self._make_connected_sensor_list(server_info)
            )
        self._update_ui()

    def _make_connected_sensor_list(self, server_info: a121.ServerInfo) -> list[tuple[str, int]]:
        connected_sensors: list[tuple[str, int]] = []

        for k, v in server_info.sensor_infos.items():
            if v.connected:
                connected_sensors.append((str(k), k))

        return connected_sensors
