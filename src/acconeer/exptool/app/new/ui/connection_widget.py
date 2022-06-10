from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

import acconeer.exptool as et
from acconeer.exptool.app.new import utils
from acconeer.exptool.app.new.app_model import AppModel, ConnectionInterface, ConnectionState
from acconeer.exptool.app.new.qt_subclasses import AppModelAwareWidget


class _ConnectAndDisconnectButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

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

        self.setText(TEXTS[app_model.connection_state])
        self.setEnabled(app_model.connection_state in ENABLED_STATES)


class _SocketConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model
        layout = QGridLayout()

        self.ip_line_edit = QLineEdit()
        self.ip_line_edit.setPlaceholderText("<IP address>")
        self.ip_line_edit.editingFinished.connect(self._on_line_edit)
        layout.addWidget(self.ip_line_edit)

        self.setLayout(layout)

    def _on_line_edit(self):
        self.app_model.set_socket_connection_ip(self.ip_line_edit.text())

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_app_model_error(self, exception: Exception) -> None:
        utils.show_error_pop_up("Client Error", str(exception))


class _SerialConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model

        layout = QGridLayout()

        self.port_combo_box = QComboBox()
        self.port_combo_box.currentTextChanged.connect(self._on_combo_box_change)
        layout.addWidget(self.port_combo_box, 0, 0)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_ports)
        layout.addWidget(refresh_button, 0, 1)

        self.refresh_ports()
        self.setLayout(layout)

    def refresh_ports(self) -> None:
        tagged_ports = et.utils.get_tagged_serial_ports()  # type: ignore[attr-defined]

        self.port_combo_box.clear()
        for port, tag in tagged_ports:
            label = port if tag is None else f"{port} ({tag})"
            self.port_combo_box.addItem(label, port)

    def _on_combo_box_change(self) -> None:
        self.app_model.set_serial_connection_port(self.port_combo_box.currentData())

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_app_model_error(self, exception: Exception) -> None:
        utils.show_error_pop_up("Client Error", str(exception))


class ClientConnectionWidget(AppModelAwareWidget):
    stacked_layout: QStackedLayout

    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_model, parent)

        self.app_model = app_model

        self.main_layout = QVBoxLayout()

        self.interface_dd = QComboBox()

        self.interface_dd.addItem("Socket", userData=ConnectionInterface.SOCKET)
        self.interface_dd.addItem("Serial", userData=ConnectionInterface.SERIAL)

        self.interface_dd.currentIndexChanged.connect(self._on_interface_dd_change)
        self.main_layout.addWidget(self.interface_dd)

        self.stacked_layout = QStackedLayout()
        self.stacked_layout.addWidget(_SocketConnectionWidget(app_model))
        self.stacked_layout.addWidget(_SerialConnectionWidget(app_model))
        self.main_layout.addLayout(self.stacked_layout)

        self.main_layout.addWidget(_ConnectAndDisconnectButton(app_model, self))
        self.main_layout.addStretch()

        self.setLayout(self.main_layout)

    def _on_interface_dd_change(self) -> None:
        self.app_model.set_connection_interface(self.interface_dd.currentData())

    def on_app_model_error(self, exception: Exception) -> None:
        pass

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(
            app_model.connection_state in {ConnectionState.DISCONNECTED, ConnectionState.CONNECTED}
        )
        self.interface_dd.setEnabled(
            app_model.connection_state != ConnectionState.CONNECTED,
        )

        interface_index = self.interface_dd.findData(app_model.connection_interface)
        if interface_index == -1:
            raise RuntimeError

        self.interface_dd.setCurrentIndex(interface_index)
        self.stacked_layout.setCurrentIndex(interface_index)
