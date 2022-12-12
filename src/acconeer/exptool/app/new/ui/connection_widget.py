# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import qtawesome as qta

from PySide6 import QtCore
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new._enums import ConnectionInterface, ConnectionState
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.qt_subclasses import AppModelAwareWidget

from .misc import BUTTON_ICON_COLOR, SerialPortComboBox, USBDeviceComboBox


class _ConnectAndDisconnectButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setFixedWidth(120)

        app_model.sig_notify.connect(self._on_app_model_update)

        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        if self.app_model.connection_state == ConnectionState.DISCONNECTED:
            self.app_model.connect_client()
        elif self.app_model.connection_state == ConnectionState.CONNECTED:
            self.app_model.disconnect_client()
        else:
            raise RuntimeError

    def _on_app_model_update(self, app_model: AppModel) -> None:
        TEXTS = {
            ConnectionState.DISCONNECTED: "Connect",
            ConnectionState.CONNECTING: "Connecting...",
            ConnectionState.CONNECTED: "Disconnect",
            ConnectionState.DISCONNECTING: "Disconnecting...",
        }
        ENABLED_STATES = {ConnectionState.CONNECTED, ConnectionState.DISCONNECTED}
        ICONS = {
            ConnectionState.DISCONNECTED: "fa5s.link",
            ConnectionState.CONNECTING: "fa5s.link",
            ConnectionState.CONNECTED: "fa5s.unlink",
            ConnectionState.DISCONNECTING: "fa5s.unlink",
        }
        TOOLTIPS = {
            ConnectionState.DISCONNECTED: "Connect to device using specified interface",
            ConnectionState.CONNECTING: "Connecting...",
            ConnectionState.CONNECTED: "Disconnect the device",
            ConnectionState.DISCONNECTING: "Disconnecting...",
        }

        self.setText(TEXTS[app_model.connection_state])
        self.setEnabled(
            app_model.connection_state in ENABLED_STATES
            and app_model.plugin_state.is_steady
            and app_model.is_connect_ready()
        )
        self.setIcon(qta.icon(ICONS[app_model.connection_state], color=BUTTON_ICON_COLOR))
        self.setToolTip(TOOLTIPS[app_model.connection_state])


class _SocketConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.ip_line_edit = QLineEdit(self)
        self.ip_line_edit.setPlaceholderText("<IP address>")
        self.ip_line_edit.editingFinished.connect(self._on_line_edit)
        self.ip_line_edit.returnPressed.connect(self._on_return_pressed)
        self.ip_line_edit.setMinimumWidth(125)
        self.layout().addWidget(self.ip_line_edit)

    def _on_line_edit(self) -> None:
        self.app_model.set_socket_connection_ip(self.ip_line_edit.text())

    def _on_return_pressed(self) -> None:
        if self.app_model.connection_state == ConnectionState.DISCONNECTED:
            self.app_model.connect_client()

    def on_app_model_update(self, app_model: AppModel) -> None:
        if not self.ip_line_edit.isModified():
            self.ip_line_edit.setText(str(app_model.socket_connection_ip))


class _SerialConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.layout().addWidget(SerialPortComboBox(app_model, self))


class _ConnectSettingsButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent, flat=True)
        self.app_model = app_model

        self.setIcon(qta.icon("fa5s.cog", color=BUTTON_ICON_COLOR))
        self.setToolTip("Advanced settings")

        self.settings_dialog = _ConnectSettingsDialog(app_model, self)

        app_model.sig_notify.connect(self._on_app_model_update)
        self.clicked.connect(self._on_click)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.connection_state == ConnectionState.DISCONNECTED)

    def _on_click(self) -> None:
        self.settings_dialog.exec()


class _ConnectSettingsBaudrate(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)

        self.baudrate_line_edit = QLineEdit(self)
        validator = QRegularExpressionValidator(self)
        # Empty string or integer
        validator.setRegularExpression(QtCore.QRegularExpression("(^[0-9]+$|^$)"))
        self.baudrate_line_edit.setValidator(validator)
        self.baudrate_line_edit.setPlaceholderText("auto")
        self.baudrate_line_edit.textEdited.connect(self._on_text_edit)
        self.baudrate_line_edit.editingFinished.connect(self._on_line_edit)
        self.baudrate_line_edit.setFixedWidth(125)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Baudrate:"))
        layout.addWidget(self.baudrate_line_edit)

        self.setLayout(layout)
        self.setToolTip("Override default baudrate of serial device")

    def _on_text_edit(self) -> None:
        if not self.baudrate_line_edit.text():
            self.baudrate_line_edit.setStyleSheet("* {font: italic}")
        else:
            self.baudrate_line_edit.setStyleSheet("* {}")

    def _on_line_edit(self) -> None:
        baudrate_text = self.baudrate_line_edit.text()
        baudrate = None if baudrate_text == "" else int(baudrate_text)
        self.app_model.set_overridden_baudrate(baudrate)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        if not self.baudrate_line_edit.isModified():
            if app_model.overridden_baudrate is None:
                self.baudrate_line_edit.setText("")
            else:
                self.baudrate_line_edit.setText(str(app_model.overridden_baudrate))
            self._on_text_edit()


class _ConnectSettingsDialog(QDialog):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model
        app_model.sig_notify.connect(self._on_app_model_update)

        self.auto_connect_check_box = QCheckBox("Auto-connect", self)
        self.auto_connect_check_box.setToolTip("Enables auto-connect of device")
        self.auto_connect_check_box.stateChanged.connect(self._auto_connect_on_state_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(_ConnectSettingsBaudrate(app_model, self))
        layout.addWidget(self.auto_connect_check_box)

        self.setWindowTitle("Advanced settings")
        self.setMinimumWidth(300)
        self.setLayout(layout)

    def _auto_connect_on_state_changed(self) -> None:
        self.app_model.set_autoconnect_enabled(self.auto_connect_check_box.isChecked())

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.auto_connect_check_box.setChecked(app_model.autoconnect_enabled)


class _SimulatedConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model
        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)


class ClientConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(app_model, parent)

        self.app_model = app_model

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.interface_dd = QComboBox(self)
        self.interface_dd.setMinimumWidth(110)

        self.layout().addWidget(self.interface_dd)

        self.interface_dd.addItem("Socket", userData=ConnectionInterface.SOCKET)
        self.interface_dd.addItem("Serial", userData=ConnectionInterface.SERIAL)
        self.interface_dd.addItem("USB", userData=ConnectionInterface.USB)
        self.interface_dd.addItem("Simulated", userData=ConnectionInterface.SIMULATED)

        self.interface_dd.currentIndexChanged.connect(self._on_interface_dd_change)

        self.stacked = QStackedWidget(self)
        self.stacked.setStyleSheet("QStackedWidget {background-color: transparent;}")
        self.stacked.addWidget(_SocketConnectionWidget(app_model, self.stacked))
        self.stacked.addWidget(_SerialConnectionWidget(app_model, self.stacked))
        self.stacked.addWidget(USBDeviceComboBox(app_model, self.stacked))
        self.stacked.addWidget(_SimulatedConnectionWidget(app_model, self.stacked))
        self.layout().addWidget(self.stacked)

        self.layout().addWidget(_ConnectSettingsButton(app_model, self))
        self.layout().addWidget(_ConnectAndDisconnectButton(app_model, self))

        self.layout().addStretch(1)

    def _on_interface_dd_change(self) -> None:
        self.app_model.set_connection_interface(self.interface_dd.currentData())

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.stacked.setEnabled(
            app_model.connection_state == ConnectionState.DISCONNECTED,
        )
        self.interface_dd.setEnabled(
            app_model.connection_state == ConnectionState.DISCONNECTED,
        )

        interface_index = self.interface_dd.findData(app_model.connection_interface)
        if interface_index == -1:
            raise RuntimeError

        self.interface_dd.setCurrentIndex(interface_index)
        self.stacked.setCurrentIndex(interface_index)


class GenerationSelection(QComboBox):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.addItem("A121")
        self.setEnabled(False)
