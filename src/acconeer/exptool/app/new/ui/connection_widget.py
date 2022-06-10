from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
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
from acconeer.exptool import a121
from acconeer.exptool.app.new import interactions, utils
from acconeer.exptool.app.new.app_model import AppModel, ConnectionInterface, ConnectionState
from acconeer.exptool.app.new.qt_subclasses import AppModelAwareWidget


class _ConnectAndDisconnectButtons(QWidget):
    sig_connect_clicked = Signal()
    sig_disconnect_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        # TODO: make these not be comically large.
        super().__init__(parent)

        connect_button = QPushButton("Connect")
        connect_button.clicked.connect(self.sig_connect_clicked.emit)

        disconnect_button = QPushButton("Disconnect")
        disconnect_button.clicked.connect(self.sig_disconnect_clicked.emit)

        self._layout = QStackedLayout()
        self._layout.addWidget(connect_button)
        self._layout.addWidget(disconnect_button)
        self.setLayout(self._layout)

    def show_connect_button(self) -> None:
        self._layout.setCurrentIndex(0)

    def show_disconnect_button(self) -> None:
        self._layout.setCurrentIndex(1)


class _SocketConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model
        layout = QGridLayout()

        self.ip_line_edit = QLineEdit()
        self.ip_line_edit.setPlaceholderText("<IP address>")
        layout.addWidget(self.ip_line_edit)

        self.connection_buttons = _ConnectAndDisconnectButtons(self)
        self.connection_buttons.sig_connect_clicked.connect(
            lambda: interactions.put_client_connect_request(
                self.app_model, a121.ClientInfo(ip_address=self.ip_line_edit.text())
            )
        )
        self.connection_buttons.sig_disconnect_clicked.connect(
            lambda: interactions.put_client_disconnect_request(self.app_model)
        )

        layout.addWidget(self.connection_buttons)
        self.setLayout(layout)

    def on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.connection_state == ConnectionState.DISCONNECTED:
            self.connection_buttons.show_connect_button()
        elif app_model.connection_state == ConnectionState.CONNECTED:
            self.connection_buttons.show_disconnect_button()

    def on_app_model_error(self, exception: Exception) -> None:
        utils.show_error_pop_up("Client Error", str(exception))


class _SerialConnectionWidget(AppModelAwareWidget):
    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(app_model, parent)
        self.app_model = app_model

        layout = QGridLayout()

        self.port_combo_box = QComboBox()
        layout.addWidget(self.port_combo_box, 0, 0)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_ports)
        layout.addWidget(refresh_button, 0, 1)

        self.baudrate_line_edit = QLineEdit()
        self.baudrate_line_edit.setEnabled(False)  # TODO
        self.baudrate_line_edit.setPlaceholderText("Baudrate")
        layout.addWidget(self.baudrate_line_edit, 1, 0, 1, 2)

        self.connection_buttons = _ConnectAndDisconnectButtons(self)
        self.connection_buttons.sig_connect_clicked.connect(
            lambda: interactions.put_client_connect_request(
                self.app_model,
                a121.ClientInfo(
                    serial_port=self.port_combo_box.currentData(),
                    override_baudrate=None,  # TODO
                ),
            )
        )
        self.connection_buttons.sig_disconnect_clicked.connect(
            lambda: interactions.put_client_disconnect_request(self.app_model)
        )
        layout.addWidget(self.connection_buttons, 2, 0, 1, 2)

        self.refresh_ports()
        self.setLayout(layout)

    def refresh_ports(self) -> None:
        tagged_ports = et.utils.get_tagged_serial_ports()  # type: ignore[attr-defined]

        self.port_combo_box.clear()
        for port, tag in tagged_ports:
            label = port if tag is None else f"{port} ({tag})"
            self.port_combo_box.addItem(label, port)

    def on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.connection_state == ConnectionState.DISCONNECTED:
            self.connection_buttons.show_connect_button()
        elif app_model.connection_state == ConnectionState.CONNECTED:
            self.connection_buttons.show_disconnect_button()

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
