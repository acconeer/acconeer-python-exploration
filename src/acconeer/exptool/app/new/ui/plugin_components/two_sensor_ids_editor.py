# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from acconeer.exptool import a121

from . import pidgets


class TwoSensorIdsEditor(QWidget):

    sig_update = Signal(object)
    sensor_ids: t.Optional[list[int]]

    def __init__(self, name_label_texts: list[str]):
        super().__init__()

        self._sensor_id_pidget_1 = pidgets.SensorIdParameterWidgetFactory(
            name_label_text=name_label_texts[0], items=[]
        ).create(self)
        self._sensor_id_pidget_2 = pidgets.SensorIdParameterWidgetFactory(
            name_label_text=name_label_texts[1], items=[]
        ).create(self)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.layout().addWidget(self._sensor_id_pidget_1)
        self.layout().addWidget(self._sensor_id_pidget_2)

        self._sensor_id_pidget_1.sig_parameter_changed.connect(
            lambda sensor_id: self.handle_pidget_signal(sensor_id, sensor_id_position=0)
        )
        self._sensor_id_pidget_2.sig_parameter_changed.connect(
            lambda sensor_id: self.handle_pidget_signal(sensor_id, sensor_id_position=1)
        )

        self.sensor_ids = None

    def set_data(self, sensor_ids: t.Optional[list[int]]) -> None:
        if sensor_ids is None:
            self.sensor_ids = None
        else:
            if len(sensor_ids) == 2:
                self.sensor_ids = sensor_ids
            else:
                raise ValueError("Length of sensor list is not equal to two.")

    def sync(self):
        if self.sensor_ids is not None:
            self._sensor_id_pidget_1.set_parameter(self.sensor_ids[0])
            self._sensor_id_pidget_2.set_parameter(self.sensor_ids[1])
            self.setEnabled(True)
        else:
            self.setEnabled(False)

    def update_available_sensor_list(self, server_info: t.Optional[a121.ServerInfo]) -> None:
        self._sensor_id_pidget_1.update_available_sensor_list(server_info)
        self._sensor_id_pidget_2.update_available_sensor_list(server_info)

    def handle_pidget_signal(self, sensor_id: int, sensor_id_position: int) -> None:
        if self.sensor_ids is not None:
            self.sensor_ids[sensor_id_position] = sensor_id
            self.sig_update.emit(self.sensor_ids)
