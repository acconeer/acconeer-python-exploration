# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import platform
import webbrowser
from typing import Optional

import pyperclip
import qtawesome as qta

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from acconeer.exptool.app.new._enums import ConnectionInterface
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app_model import AppModel


BUTTON_ICON_COLOR = "#0081db"


class ExceptionWidget(QMessageBox):
    def __init__(
        self,
        parent: QWidget,
        *,
        exc: Exception,
        traceback_str: Optional[str] = None,
        title: str = "Error",
    ) -> None:
        super().__init__(parent)

        self.setIcon(QMessageBox.Warning)
        self.setStandardButtons(QMessageBox.Ok)

        self.setWindowTitle(title)
        self.setText(str(exc))

        try:
            raise exc
        except HandledException:
            pass
        except Exception:
            self.setInformativeText("<b>Unhandled error - please file a bug</b>")

        if traceback_str:
            self.setDetailedText(traceback_str)
            copy_button = QPushButton(self)
            copy_button.setText("Copy details")
            self.addButton(copy_button, QMessageBox.ButtonRole.ActionRole)
            copy_button.clicked.disconnect()
            copy_button.clicked.connect(self._on_copy_clicked)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.setFixedWidth(500)

    def _on_copy_clicked(self) -> None:
        detailed_text = self.detailedText()
        if detailed_text:
            pyperclip.copy(detailed_text)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.close()


class VerticalSeparator(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(5, 5, 5, 5)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.VLine)
        self.layout().addWidget(frame)


class SerialPortComboBox(QComboBox):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)
        self.currentTextChanged.connect(self._on_change)

    def _on_change(self) -> None:
        self.app_model.set_serial_connection_port(self.currentData())

    def _on_app_model_update(self, app_model: AppModel) -> None:
        tagged_ports = app_model.available_tagged_ports

        ports = [port for port, _ in tagged_ports]
        view_ports = [self.itemData(i) for i in range(self.count())]

        with QtCore.QSignalBlocker(self):
            if ports != view_ports:
                self.clear()
                for port, tag in tagged_ports:
                    label = port if tag is None else f"{port} ({tag})"
                    self.addItem(label, port)

            index = self.findData(app_model.serial_connection_port)
            self.setCurrentIndex(index)


class USBDeviceComboBox(QComboBox):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)
        self.currentTextChanged.connect(self._on_change)
        self.setMinimumWidth(175)

    def _on_change(self) -> None:
        self.app_model.set_usb_connection_port(self.currentData())

    def _on_app_model_update(self, app_model: AppModel) -> None:
        usb_devices = app_model.available_usb_devices

        view_ports = [self.itemData(i) for i in range(self.count())]

        with QtCore.QSignalBlocker(self):
            if usb_devices != view_ports:
                self.clear()
                for usb_device in usb_devices:
                    self.addItem(usb_device.name, usb_device)

            index = self.findData(app_model.usb_connection_device)
            self.setCurrentIndex(index)


class ConnectionHint(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)
        app_model.sig_notify.connect(self._on_app_model_update)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.icon = qta.IconWidget()
        self.icon.setIcon(qta.icon("fa.warning", color="#ff9e00"))
        self.layout().addWidget(self.icon)

        self.label = QLabel(self)
        self.label.setText("You may experience stability issues")
        self.layout().addWidget(self.label)

        self.button = QPushButton(self)
        self.button.setIcon(qta.icon("fa5s.external-link-alt", color=BUTTON_ICON_COLOR))
        self.button.setText("How to fix")
        self.button.clicked.connect(self._on_click)
        self.layout().addWidget(self.button)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        hide = not self._should_show(app_model)
        self.icon.setHidden(hide)
        self.label.setHidden(hide)
        self.button.setHidden(hide)

    def _on_click(self) -> None:
        url = r"https://docs.acconeer.com/en/latest/evk_setup/xc120_xe121.html"
        webbrowser.open_new_tab(url)

    @staticmethod
    def _should_show(app_model: AppModel) -> bool:
        if platform.system().lower() != "windows":
            return False

        if app_model.connection_interface != ConnectionInterface.SERIAL:
            return False

        port = app_model.serial_connection_port
        if port is None:
            return False

        tag = dict(app_model.available_tagged_ports).get(port, None)

        if tag is None:
            return False

        return "xc120" in tag.lower()
