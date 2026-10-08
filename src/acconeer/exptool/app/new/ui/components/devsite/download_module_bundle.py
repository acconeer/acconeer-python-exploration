# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from acconeer.exptool._artifact_repository import (
    Artifact,
    DevSiteRepository,
    LoginRequiredError,
)
from acconeer.exptool.app.new.storage import get_temp_dir
from acconeer.exptool.app.new.ui.background_task import BGTask
from acconeer.exptool.app.new.ui.components.devsite._utils import (
    get_internet_related_error_message,
)
from acconeer.exptool.app.new.ui.components.devsite.license import LicenseDialog
from acconeer.exptool.app.new.ui.components.devsite.login import LoginDialog
from acconeer.exptool.app.new.ui.utils import FeedbackStyleSheet


class _DownloadDialog(QDialog):
    """Downloads the module bundle in the background, modally.

    ``exec()`` returns ``Accepted`` with ``downloaded_path`` set, or
    ``Rejected`` with ``error`` set.

    The download cannot be cancelled, so the window close button and Escape
    are ignored; dismissing the dialog without also stopping the background
    download would make a later success silently discarded.
    """

    def __init__(self, repository: DevSiteRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Downloading")
        self.downloaded_path: Path | None = None
        self.error: Exception | None = None

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Downloading, please wait ..."))
        self.setLayout(layout)

        BGTask.create_task(
            repository.download,
            (Artifact.MODULE_BUNDLE, str(get_temp_dir())),
            return_cb=self._handle_success,
            exception_cb=self._handle_exception,
        )

    def _handle_success(self, path_and_version: tuple[str, str]) -> None:
        downloaded_path, _version = path_and_version
        self.downloaded_path = Path(downloaded_path)
        self.accept()

    def _handle_exception(self, exception: Exception) -> None:
        self.error = exception
        self.reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)


def _log_in(parent: QWidget, feedback: str | None = None) -> DevSiteRepository | None:
    login_dialog = LoginDialog(parent)
    if feedback is not None:
        login_dialog.login_widget.set_feedback(feedback, FeedbackStyleSheet.NICE)
    if login_dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    assert login_dialog.repository is not None
    return login_dialog.repository


def download_module_bundle(parent: QWidget) -> Path | None:
    """Walks the user through login, license and download of the module bundle.

    Returns the downloaded file, or None if the user cancelled or the
    download failed (reported via a message box).
    """
    repository = DevSiteRepository.from_saved_login()
    if not repository.has_logged_in_previously():
        logged_in_repository = _log_in(parent)
        if logged_in_repository is None:
            return None
        repository = logged_in_repository

    license_dialog = LicenseDialog(parent)
    if license_dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    while True:
        download_dialog = _DownloadDialog(repository, parent)
        if download_dialog.exec() == QDialog.DialogCode.Accepted:
            return download_dialog.downloaded_path

        if not isinstance(download_dialog.error, LoginRequiredError):
            assert download_dialog.error is not None
            QMessageBox.critical(
                parent,
                "Download failed",
                get_internet_related_error_message(download_dialog.error),
            )
            return None

        repository.forget_login()
        logged_in_repository = _log_in(
            parent,
            "Your developer.acconeer.com login has expired. Log in again to download.",
        )
        if logged_in_repository is None:
            return None
        repository = logged_in_repository
