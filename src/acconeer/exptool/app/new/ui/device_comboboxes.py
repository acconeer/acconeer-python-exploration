# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import abc
from typing import Optional, Sequence

from PySide6 import QtCore
from PySide6.QtWidgets import QComboBox, QWidget

from acconeer.exptool._core.communication.comm_devices import CommDevice, SerialDevice, USBDevice
from acconeer.exptool.app.new.app_model import AppModel


class CommDeviceComboBox(QComboBox):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)
        self.currentTextChanged.connect(self._on_change)
        self.setMinimumWidth(175)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        devices = self._get_available_devices()

        view_ports = [self.itemData(i) for i in range(self.count())]

        with QtCore.QSignalBlocker(self):
            if devices != view_ports:
                self.clear()
                for device in devices:
                    self.addItem(device.display_name(), device)

            current_device = self._get_current_device()

            # QComboBox.findData can't be used since since it doesn't
            # always match different but content wise identical objects.
            index = -1
            for i in range(self.count()):
                if self.itemData(i) == current_device:
                    index = i
                    break
            self.setCurrentIndex(index)

            self.setEnabled(self.count() > 0)
            if self.count() == 0:
                self.addItem("No device available")

    @abc.abstractmethod
    def _on_change(self) -> None:
        pass

    @abc.abstractmethod
    def _get_available_devices(self) -> Sequence[CommDevice]:
        pass

    @abc.abstractmethod
    def _get_current_device(self) -> Optional[CommDevice]:
        pass


class SerialPortComboBox(CommDeviceComboBox):
    def _on_change(self) -> None:
        self.app_model.set_serial_connection_device(self.currentData())

    def _get_available_devices(self) -> Sequence[SerialDevice]:
        return self.app_model.available_serial_devices

    def _get_current_device(self) -> Optional[SerialDevice]:
        return self.app_model.serial_connection_device


class USBDeviceComboBox(CommDeviceComboBox):
    def _on_change(self) -> None:
        self.app_model.set_usb_connection_device(self.currentData())

    def _get_available_devices(self) -> Sequence[USBDevice]:
        return self.app_model.available_usb_devices

    def _get_current_device(self) -> Optional[USBDevice]:
        return self.app_model.usb_connection_device
