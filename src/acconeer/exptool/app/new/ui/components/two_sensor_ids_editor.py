# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from . import pidgets


class TwoSensorIdsEditor(QWidget):
    sig_update = Signal(object)

    def __init__(self, name_label_texts: list[str]):
        super().__init__()

        self._sensor_id_pidget_1 = pidgets.SensorIdPidgetFactory(
            name_label_text=name_label_texts[0], items=[]
        ).create(self)
        self._sensor_id_pidget_2 = pidgets.SensorIdPidgetFactory(
            name_label_text=name_label_texts[1], items=[]
        ).create(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._sensor_id_pidget_1)
        layout.addWidget(self._sensor_id_pidget_2)

        self._sensor_id_pidget_1.sig_update.connect(lambda: self.sig_update.emit(self.sensor_ids))
        self._sensor_id_pidget_2.sig_update.connect(lambda: self.sig_update.emit(self.sensor_ids))

        self.setLayout(layout)

    @property
    def sensor_ids(self) -> list[int]:
        return [
            self._sensor_id_pidget_1.get_data(),
            self._sensor_id_pidget_2.get_data(),
        ]

    def set_data(self, sensor_ids: list[int]) -> None:
        assert len(sensor_ids) == 2
        self._sensor_id_pidget_1.set_data(sensor_ids[0])
        self._sensor_id_pidget_2.set_data(sensor_ids[1])

    def set_selectable_sensors(self, sensor_list: list[int]) -> None:
        self._sensor_id_pidget_1.set_selectable_sensors(sensor_list)
        self._sensor_id_pidget_2.set_selectable_sensors(sensor_list)
