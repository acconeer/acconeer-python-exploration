# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from acconeer.exptool._artifact_repository import (
    Artifact,
    ArtifactRepository,
    LoginRequiredError,
    create_artifact_repository,
)
from acconeer.exptool.app.new.storage import get_algo_bundle_path, get_temp_dir
from acconeer.exptool.app.new.ui.background_task import BGTask
from acconeer.exptool.app.new.ui.components.devsite._utils import (
    get_internet_related_error_message,
)
from acconeer.exptool.app.new.ui.components.devsite.license import LicenseDialog
from acconeer.exptool.app.new.ui.components.devsite.login import LoginDialog
from acconeer.exptool.app.new.ui.utils import FeedbackStyleSheet


class _DownloadDialog(QDialog):
    """Downloads the algo bundle in the background, modally.

    ``exec()`` returns ``Accepted`` with ``downloaded_path`` set, or
    ``Rejected`` with ``error`` set.

    The download cannot be cancelled, so the window close button and Escape
    are ignored; dismissing the dialog without also stopping the background
    download would make a later success silently discarded.
    """

    def __init__(self, repository: ArtifactRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Downloading")
        self.downloaded_path: Path | None = None
        self.error: Exception | None = None

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Downloading, please wait ..."))
        self.setLayout(layout)

        BGTask.create_task(
            repository.download,
            (Artifact.ALGO_BUNDLE, str(get_temp_dir())),
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


def _log_in(repository: ArtifactRepository, parent: QWidget, feedback: str | None = None) -> bool:
    login_dialog = LoginDialog(repository, parent)
    if feedback is not None:
        login_dialog.login_widget.set_feedback(feedback, FeedbackStyleSheet.NICE)
    return login_dialog.exec() == QDialog.DialogCode.Accepted


def download_algo_bundle(parent: QWidget) -> Path | None:
    """Walks the user through login, license and download of the algo bundle.

    Returns where the downloaded file is stored, or None if the user
    cancelled or the download failed (reported via a message box).
    """
    repository = create_artifact_repository()
    if not repository.has_logged_in_previously() and not _log_in(repository, parent):
        return None

    license_dialog = LicenseDialog(parent)
    if license_dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    while True:
        download_dialog = _DownloadDialog(repository, parent)
        if download_dialog.exec() == QDialog.DialogCode.Accepted:
            assert download_dialog.downloaded_path is not None
            return Path(shutil.move(download_dialog.downloaded_path, get_algo_bundle_path()))

        if not isinstance(download_dialog.error, LoginRequiredError):
            assert download_dialog.error is not None
            QMessageBox.critical(
                parent,
                "Download failed",
                get_internet_related_error_message(download_dialog.error),
            )
            return None

        repository.forget_login()
        if not _log_in(repository, parent, "Your login has expired. Log in again to download."):
            return None
