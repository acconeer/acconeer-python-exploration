from __future__ import annotations

import importlib
import logging

import serial

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QMovie
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import acconeer.exptool as et
from acconeer.exptool.app import resources  # type: ignore[attr-defined]
from acconeer.exptool.app.new.app_model import AppModel, ConnectionState
from acconeer.exptool.flash import find_flash_port, flash_image  # type: ignore[import]


log = logging.getLogger(__name__)


class _FlashThread(QThread):
    flash_failed = Signal(str)
    flash_done = Signal()

    def __init__(self, bin_file: str, flash_port: serial.tools.list_ports.ListPortInfo) -> None:
        super().__init__()
        self.bin_file = bin_file
        self.flash_port = flash_port

    def run(self) -> None:
        try:
            flash_image(self.bin_file, self.flash_port)
            self.flash_done.emit()
        except Exception as e:
            log.error(str(e))
            self.flash_failed.emit(str(e))


class _FlashDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setWindowTitle("Flash tool")
        self.setMinimumWidth(200)

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignCenter)
        vbox.setSizeConstraint(QVBoxLayout.SetMinimumSize)

        self.loading = QLabel()
        self.loading.setAlignment(Qt.AlignCenter)

        loader_gif = None
        with importlib.resources.path(resources, "loader.gif") as path:
            loader_gif = path

        self.flash_movie = QMovie(str(loader_gif))
        self.loading.setMovie(self.flash_movie)
        vbox.addWidget(self.loading)

        self.flash_label = QLabel(self)
        self.flash_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        self.flash_label.setAlignment(Qt.AlignCenter)
        vbox.addWidget(self.flash_label)

        self.setLayout(vbox)

    def flash(self, bin_file, flash_port):
        self.flash_thread = _FlashThread(bin_file, flash_port)
        self.flash_thread.started.connect(self._flash_start)
        self.flash_thread.finished.connect(self.flash_thread.deleteLater)
        self.flash_thread.finished.connect(self._flash_stop)
        self.flash_thread.flash_done.connect(self._flash_done)
        self.flash_thread.flash_failed.connect(self._flash_failed)

        self.flash_thread.start()
        self._flashing = True
        self.exec()

    def _flash_start(self) -> None:
        self.flash_label.setText("Flashing...")
        self.flash_movie.start()

    def _flash_stop(self) -> None:
        self.flash_movie.stop()
        self.loading.hide()
        self._flashing = False

    def _flash_done(self) -> None:
        self.flash_label.setText("Flashing done!")

    def _flash_failed(self, msg: str) -> None:
        self.flash_label.setText(f"Flashing failed ({msg})!")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._flashing:
            self.flash_thread.terminate()
            self.flash_thread.wait()
        super().closeEvent(event)


class _FlashPopup(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setWindowTitle("Flash tool")
        self.setMinimumWidth(350)

        self.flash_port = None
        self.bin_file = None

        layout = QFormLayout(self)

        self.file_label = QLineEdit("<Select an bin file>")
        self.file_label.setReadOnly(True)

        browse_button = QPushButton("Browse", self)
        browse_button.clicked.connect(self._browse_file)
        layout.addRow(browse_button, self.file_label)

        self.port_combo_box = QComboBox(self)
        self.port_combo_box.currentTextChanged.connect(self._on_port_combo_box_change)

        refresh_button = QPushButton("Refresh", self)
        refresh_button.clicked.connect(self._refresh_ports)
        layout.addRow(refresh_button, self.port_combo_box)

        self.flash_button = QPushButton("Flash", self)
        self.flash_button.clicked.connect(self._flash)
        self.flash_button.setEnabled(False)
        layout.addRow(self.flash_button)

        self.setLayout(layout)

        self.browse_file_dialog = QFileDialog(None)
        self.browse_file_dialog.setNameFilter("Bin files (*.bin)")

        self.flash_dialog = _FlashDialog(self)

        self._refresh_ports()

    def _refresh_ports(self) -> None:
        tagged_ports = et.utils.get_tagged_serial_ports()

        self.port_combo_box.clear()
        for port, tag in tagged_ports:
            if tag:
                label = f"{port} ({tag})"
                self.port_combo_box.addItem(label, port)

    def _browse_file(self) -> None:
        if self.browse_file_dialog.exec():
            filenames = self.browse_file_dialog.selectedFiles()
            self.bin_file = filenames[0]
            self.file_label.setText(self.bin_file)

        self.flash_button.setEnabled(self.flash_port is not None and self.bin_file is not None)

    def _flash(self) -> None:
        flash_port = find_flash_port(self.flash_port)

        self.flash_dialog.flash(self.bin_file, flash_port)

    def _on_port_combo_box_change(self) -> None:
        self.flash_port = self.port_combo_box.currentData()

        self.flash_button.setEnabled(self.flash_port is not None and self.bin_file is not None)


class FlashButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setFixedWidth(100)
        self.setText("Flash")

        app_model.sig_notify.connect(self._on_app_model_update)
        self.pop_up = _FlashPopup(self)
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        self.pop_up.exec()

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.connection_state == ConnectionState.DISCONNECTED)
