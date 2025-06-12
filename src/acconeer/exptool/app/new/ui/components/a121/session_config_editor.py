# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import copy
import logging
from typing import Any, List, Optional

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool import a121
from acconeer.exptool._core.entities.validation_result import Criticality
from acconeer.exptool.a121._core import utils
from acconeer.exptool.app.new.ui.components import pidgets
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.components.group_box import GroupBox
from acconeer.exptool.app.new.ui.components.json_save_load_buttons import (
    create_json_save_load_buttons,
)
from acconeer.exptool.app.new.ui.icons import PLUS, REMOVE

from .sensor_config_editor import SensorConfigEditor


log = logging.getLogger(__name__)


def session_or_sensor_config_json_to_session_config(json_str: str) -> a121.SessionConfig:
    try:
        return a121.SessionConfig.from_json(json_str)
    except KeyError:
        return a121.SessionConfig(a121.SensorConfig.from_json(json_str))


class SensorIdCombobox(DataEditor[Optional[int]]):
    sig_update = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self._selectable_sensors: list[int] = []
        self._combobox = pidgets.PidgetComboBox(self)
        self._combobox.currentIndexChanged.connect(self._emit_data_at_index)
        self.set_data(None)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combobox)

        self.setLayout(layout)

    def setEnabled(self, enabled: bool) -> None:
        """Resets the DataEditor.setEnabled behavior to the default QWidget"""
        QWidget.setEnabled(self, enabled)

    @staticmethod
    def _get_combobox_model(
        data: Optional[int], selectable: list[int]
    ) -> list[tuple[str, Optional[int]]]:
        base: list[tuple[str, Optional[int]]] = [(str(sid), sid) for sid in selectable]
        if data is None:
            return [("-", None)] + base

        if data in selectable:
            return base
        else:
            return [(f"{data} (unavailable)", data)] + base

    def _update_combobox_model(self, data: Optional[int], selectable: list[int]) -> None:
        with QSignalBlocker(self):
            self._combobox.clear()

            for label, sid in self._get_combobox_model(data, selectable):
                self._combobox.addItem(label, sid)

            self._combobox.setCurrentIndex(self._combobox.findData(data))

    def _emit_data_at_index(self, index: int) -> None:
        self.sig_update.emit(self._combobox.itemData(index))

    def set_selectable_sensors(self, sensor_list: list[int]) -> None:
        self._selectable_sensors = sensor_list
        self._update_combobox_model(self.get_data(), sensor_list)
        self.setEnabled(sensor_list != [])

    def set_data(self, sensor_id: Optional[int]) -> None:
        with QSignalBlocker(self):
            self._combobox.setCurrentIndex(self._combobox.findData(sensor_id))
            self._update_combobox_model(sensor_id, self._selectable_sensors)

    def get_data(self) -> Optional[int]:
        try:
            return int(self._combobox.currentData())
        except TypeError:
            return None


class _SensorIdsEditor(DataEditor[List[int]]):
    _LABEL_COLUMN = 0
    _SPACING_COLUMN = 1
    _REMOVE_COLUMN = 2
    _COMBOBOX_COLUMN = 3

    sig_update = Signal(object)

    def __init__(self, multiple_sensors: bool) -> None:
        """
        Composes multiple comboboxes into a vertical layout where
        pidgets can be added or removed (except a single static combobox).

        :param multiple_sensors:
            True enables adding/removing pidgets and False gives this
            widget the appearance of a single SensorIdPidget
        """
        super().__init__()

        self._multiple_sensors = multiple_sensors
        self._selectable_sensors: list[int] = []
        self._rows: list[tuple[SensorIdCombobox, Optional[QPushButton]]] = []

        self._grid_layout = QGridLayout()
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setColumnStretch(self._LABEL_COLUMN, 0)
        self._grid_layout.setColumnStretch(self._REMOVE_COLUMN, 0)
        self._grid_layout.setColumnStretch(self._SPACING_COLUMN, 1)
        self._grid_layout.setColumnStretch(self._COMBOBOX_COLUMN, 0)

        self._add_button = QPushButton()
        self._add_button.setIcon(PLUS())
        self._add_button.setFlat(True)
        self._add_button.setFixedWidth(pidgets.WIDGET_WIDTH)
        self._add_button.setFixedWidth(125)
        self._add_button.setVisible(multiple_sensors)
        self._add_button.clicked.connect(self._create_and_add_row)
        self._add_button.clicked.connect(self._update_visuals)
        self._add_button.clicked.connect(self._emit_current_data)

        self._note_widget = QLabel()
        self._note_widget.setWordWrap(True)
        self._note_widget.setContentsMargins(5, 5, 5, 5)
        self._note_widget.hide()

        # Static row
        static_combobox = SensorIdCombobox()
        static_combobox.sig_update.connect(self._update_visuals)
        static_combobox.sig_update.connect(self._emit_current_data)

        self._rows.append((static_combobox, None))

        self._grid_layout.addWidget(QLabel("Sensors:"), 0, self._LABEL_COLUMN)
        self._grid_layout.addWidget(static_combobox, 0, self._COMBOBOX_COLUMN)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._grid_layout)
        layout.addWidget(self._add_button, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._note_widget)
        self.setLayout(layout)

    @property
    def _free_sensors(self) -> list[int]:
        """Returns a list of all the sensors that are connected but not selected"""
        return [sid for sid in self._selectable_sensors if sid not in self.get_data()]

    def _emit_current_data(self) -> None:
        self.sig_update.emit(self.get_data())

    def _get_raw_data(self) -> list[Optional[int]]:
        """Retrieves the data of the child comboboxes"""
        return [cb.get_data() for cb, _ in self._rows]

    def _update_visuals(self) -> None:
        self._add_button.setDisabled(self._free_sensors == [] or None in self._get_raw_data())

        self._add_button.setToolTip(
            "No connected sensors left"
            if self._free_sensors == []
            else (
                "Make a selection in the dashed drop down before adding a new row"
                if None in self._get_raw_data()
                else ""
            )
        )

        for combobox, _ in self._rows:
            if self._selectable_sensors == []:
                combobox.set_selectable_sensors([])
            else:
                current_data = combobox.get_data()
                if current_data is None:
                    combobox.set_selectable_sensors(sorted(self._free_sensors))
                else:
                    combobox.set_selectable_sensors(sorted(self._free_sensors + [current_data]))

    def _create_and_add_row(
        self,
    ) -> None:
        row_to_append = self._grid_layout.rowCount()

        combobox = SensorIdCombobox()
        combobox.set_selectable_sensors(self._free_sensors)
        combobox.sig_update.connect(self._update_visuals)
        combobox.sig_update.connect(self._emit_current_data)

        remove_button = QPushButton()
        remove_button.setIcon(REMOVE())
        remove_button.setToolTip("Removes this sensor")
        remove_button.setFlat(True)
        remove_button.clicked.connect(lambda: self._rows.remove((combobox, remove_button)))
        remove_button.clicked.connect(self._update_visuals)
        remove_button.clicked.connect(self._emit_current_data)
        remove_button.clicked.connect(lambda: combobox.deleteLater())
        remove_button.clicked.connect(lambda: remove_button.deleteLater())

        self._grid_layout.addWidget(combobox, row_to_append, self._COMBOBOX_COLUMN)
        self._grid_layout.addWidget(remove_button, row_to_append, self._REMOVE_COLUMN)

        self._rows.append((combobox, remove_button))

    def set_data(self, data: list[int]) -> None:
        row_balance = len(self._rows) - len(data)

        if row_balance < 0:
            num_missing_rows = -row_balance

            for _ in range(num_missing_rows):
                self._create_and_add_row()

        if row_balance > 0:
            num_redundant_rows = row_balance

            for (_, remove_button), _ in zip(reversed(self._rows), range(num_redundant_rows)):
                if remove_button is not None:
                    remove_button.click()

        for sid, (combobox, _) in zip(data, self._rows):
            combobox.set_data(sid)

    def get_data(self) -> list[int]:
        """The list of currently selected sensor ids"""
        return [sid for sid in self._get_raw_data() if sid is not None]

    def set_selectable_sensors(self, sensors: list[int]) -> None:
        self._selectable_sensors = sensors
        self._update_visuals()

    def set_note_text(
        self, message: Optional[str], criticality: Optional[Criticality] = None
    ) -> None:
        if not message:
            self._note_widget.hide()
            return

        COLOR_MAP = {
            Criticality.ERROR: "#E6635A",
            Criticality.WARNING: "#FCC842",
            None: "white",
        }

        self._note_widget.show()
        self._note_widget.setText(message)
        self._note_widget.setStyleSheet(
            f"background-color: {COLOR_MAP[criticality]}; color: white; font: bold italic;"
        )

    @property
    def is_ready(self) -> bool:
        return self._note_widget.isHidden()


class SessionConfigEditor(DataEditor[Optional[a121.SessionConfig]]):
    _session_config: Optional[a121.SessionConfig]
    _server_info: Optional[a121.ServerInfo]
    _sensor_id_pidget: pidgets.SensorIdPidget

    _update_rate_erroneous: bool

    sig_update = Signal(object)

    SPACING = 15

    def __init__(
        self,
        supports_multiple_subsweeps: bool = False,
        supports_multiple_sensors: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        self._server_info = None

        self._session_config = None
        self._update_rate_erroneous = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

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

        self._sensor_ids_editor = _SensorIdsEditor(supports_multiple_sensors)

        self._sensor_ids_editor.sig_update.connect(self._update_sensor_ids)

        self.session_group_box.layout().addWidget(self._sensor_ids_editor)

        layout.addWidget(self.session_group_box)

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
        layout.addWidget(self._sensor_config_editor)

        self.setLayout(layout)

    def set_selectable_sensors(self, sensor_list: list[int]) -> None:
        self._sensor_ids_editor.set_selectable_sensors(sensor_list)

    def set_read_only(self, read_only: bool) -> None:
        self._sensor_ids_editor.setEnabled(not read_only)
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

        self._sensor_ids_editor.set_data(self._get_sensor_ids(self._session_config))
        self._update_rate_pidget.set_data(self._session_config.update_rate)
        self._sensor_config_editor.set_data(self._get_unique_sensor_config(self._session_config))

    @staticmethod
    def _get_sensor_ids(config: a121.SessionConfig) -> list[int]:
        return [sensor_id for _, sensor_id, _ in utils.iterate_extended_structure(config.groups)]

    def get_data(self) -> Optional[a121.SessionConfig]:
        return copy.deepcopy(self._session_config)

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        self._update_rate_pidget.set_note_text(None)
        self._sensor_ids_editor.set_note_text(None)

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
            msg = "SessionConfigEditor's config is None while ValidationResults are being handled."
            raise RuntimeError(msg)

        result_handled = False

        if result.aspect == "update_rate":
            self._update_rate_pidget.set_note_text(result.message, result.criticality)
            result_handled = True
        elif result.aspect == "sensor_id":
            self._sensor_ids_editor.set_note_text(result.message, result.criticality)
            result_handled = True

        return result_handled

    def _update_update_rate(self, value: Any) -> None:
        if self._session_config is None:
            msg = "SessionConfig is None"
            raise TypeError(msg)

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

    def _update_sensor_ids(self, sensor_ids: list[int]) -> None:
        if self._session_config is None:
            msg = "SessionConfig is None"
            raise TypeError(msg)

        config = copy.deepcopy(self._session_config)

        sensor_config = self._get_unique_sensor_config(config)

        new_config = a121.SessionConfig(
            self._assemble_groups(sensor_ids, sensor_config),
            update_rate=config.update_rate,
        )

        self.set_data(new_config)
        self.sig_update.emit(new_config)

    @staticmethod
    def _get_unique_sensor_config(config: a121.SessionConfig) -> a121.SensorConfig:
        (first_config, *other_configs) = utils.iterate_extended_structure_values(config.groups)

        if any(sc != first_config for sc in other_configs):
            msg = "SessionConfig contains more than 1 unique SensorConfig"
            raise ValueError(msg)

        return first_config

    @staticmethod
    def _assemble_groups(
        sensor_ids: list[int], sensor_config: a121.SensorConfig
    ) -> list[dict[int, a121.SensorConfig]]:
        return [{sensor_id: sensor_config for sensor_id in sensor_ids}]

    def _update_sole_sensor_config(self, sensor_config: a121.SensorConfig) -> None:
        if self._session_config is None:
            raise RuntimeError

        config = a121.SessionConfig(
            self._assemble_groups(self._get_sensor_ids(self._session_config), sensor_config),
            update_rate=self._session_config.update_rate,
        )
        self.set_data(config)
        self.sig_update.emit(config)
