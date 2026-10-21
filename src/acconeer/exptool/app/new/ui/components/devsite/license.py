# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from acconeer.exptool._dev_license import DEV_LICENSE_DEFAULT_HEADER, DevLicense
from acconeer.exptool.app.new.ui.background_task import BGTask
from acconeer.exptool.app.new.ui.components.devsite._utils import (
    get_internet_related_error_message,
)


class LicenseWidget(QWidget):
    fetch_completed = Signal()
    title_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.title = DEV_LICENSE_DEFAULT_HEADER
        self._has_license = False

        self.license_text_edit = QTextEdit()
        self.license_text_edit.setReadOnly(True)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self._fetch)

        layout = QVBoxLayout()
        layout.addWidget(self.license_text_edit)
        layout.addWidget(self.retry_button)
        self.setLayout(layout)

        self._fetch()

    def has_license(self) -> bool:
        return self._has_license

    def _fetch(self) -> None:
        self.retry_button.setVisible(False)
        self.license_text_edit.setText("Downloading license ...")
        BGTask.create_task(
            self._get_dev_license,
            args=(),
            return_cb=self._populate_dev_license,
            exception_cb=self._show_fetch_error,
        )

    @staticmethod
    def _get_dev_license() -> tuple[str, str, str]:
        dev_license = DevLicense()
        dev_license.load()

        title = dev_license.get_header()
        subtitle = dev_license.get_subheader_element()
        paragraphs = "".join(dev_license.get_content_elements())

        return (title, subtitle, paragraphs)

    def _populate_dev_license(self, result: tuple[str, str, str]) -> None:
        self._has_license = True

        (title, subtitle, paragraphs) = result
        self.title = title
        self.license_text_edit.setHtml(subtitle + paragraphs)

        self.title_changed.emit(title)
        self.fetch_completed.emit()

    def _show_fetch_error(self, exception: Exception) -> None:
        self.license_text_edit.setText(
            "Could not download the license.\n" + get_internet_related_error_message(exception)
        )
        self.retry_button.setVisible(True)
        self.fetch_completed.emit()


class LicenseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.license_widget = LicenseWidget()
        self.setWindowTitle(self.license_widget.title)
        self.license_widget.title_changed.connect(self.setWindowTitle)

        self._accept_button = QPushButton("Accept")
        self._accept_button.setEnabled(False)
        self._accept_button.clicked.connect(self.accept)
        self.license_widget.fetch_completed.connect(self._handle_fetch_completed)

        self._decline_button = QPushButton("Decline")
        self._decline_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self._decline_button)
        button_layout.addWidget(self._accept_button)

        layout = QVBoxLayout()
        layout.addWidget(self.license_widget)
        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.resize(700, 600)

    def _handle_fetch_completed(self) -> None:
        self._accept_button.setEnabled(self.license_widget.has_license())
