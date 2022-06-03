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
from acconeer.exptool import a121
from acconeer.exptool.app.new.backend import Backend


class _SocketConnectionWidget(QWidget):
    def __init__(self, backend: Backend, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.backend = backend
        layout = QGridLayout()

        self.ip_line_edit = QLineEdit()
        self.ip_line_edit.setPlaceholderText("<IP address>")
        layout.addWidget(self.ip_line_edit)

        layout.addWidget(QPushButton("Connect"))

        self.setLayout(layout)

    def on_connect(self) -> None:
        self.backend.put_task(
            (
                "connect_client",
                {"client_info": a121.ClientInfo(ip_address=self.ip_line_edit.text())},
            )
        )


class _SerialConnectionWidget(QWidget):
    def __init__(self, backend: Backend, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.backend = backend

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

        layout.addWidget(QPushButton("Connect"), 2, 0, 1, 2)

        self.refresh_ports()
        self.setLayout(layout)

    def refresh_ports(self) -> None:
        tagged_ports = et.utils.get_tagged_serial_ports()  # type: ignore[attr-defined]

        self.port_combo_box.clear()
        for port, tag in tagged_ports:
            label = port if tag is None else f"{port} ({tag})"
            self.port_combo_box.addItem(label, port)

    def on_connect(self) -> None:
        self.backend.put_task(
            (
                "connect_client",
                {
                    "client_info": a121.ClientInfo(
                        serial_port=self.port_combo_box.currentData(),
                        # override_baudrate=int(self.baudrate_line_edit.text()),  # TODO
                    )
                },
            )
        )


class ClientConnectionWidget(QWidget):
    stacked_layout: QStackedLayout

    def __init__(self, backend: Backend, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.main_layout = QVBoxLayout()

        interface_dd = QComboBox()
        interface_dd.addItem("Socket")
        interface_dd.addItem("Serial")
        interface_dd.currentIndexChanged.connect(self.change_subwidget)
        self.main_layout.addWidget(interface_dd)

        self.stacked_layout = QStackedLayout()
        self.stacked_layout.addWidget(_SocketConnectionWidget(backend))
        self.stacked_layout.addWidget(_SerialConnectionWidget(backend))
        self.main_layout.addLayout(self.stacked_layout)

        self.setLayout(self.main_layout)

    def change_subwidget(self, index: int) -> None:
        if index in {0, 1}:
            self.stacked_layout.setCurrentIndex(index)
        else:
            raise ValueError(f"Combobox index is bad: {index}")
