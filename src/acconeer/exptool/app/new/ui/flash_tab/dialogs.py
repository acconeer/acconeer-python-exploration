# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from importlib.resources import as_file, files
from typing import Optional, Tuple

from requests import Response, Session
from requests.cookies import RequestsCookieJar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QMovie, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool._core.communication.comm_devices import CommDevice
from acconeer.exptool.app import resources
from acconeer.exptool.app.new.ui.misc import ExceptionWidget
from acconeer.exptool.flash import (
    BIN_FETCH_PROMPT,
    DevLicense,
    save_cookies,
)

from .threads import AuthThread, FlashThread


_WRONG_CREDENTIALS_MSG = "<font color='red'>Incorrect username (email) or password</font>"

log = logging.getLogger(__name__)


class FlashDialog(QDialog):
    flash_done = Signal(bool)
    opened = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Flash tool")
        self.setMinimumWidth(250)

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.loading = QLabel()
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        loader_gif = None
        with as_file(files(resources) / "loader.gif") as path:
            loader_gif = path

        self.flash_movie = QMovie(str(loader_gif))
        self.loading.setMovie(self.flash_movie)
        vbox.addWidget(self.loading)

        self.flash_label = QLabel(self)
        self.flash_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding
        )
        self.flash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.flash_label)

        self.ok_button = QPushButton(self)
        self.ok_button.setText("OK")
        self.ok_button.setHidden(True)
        self.ok_button.clicked.connect(self._on_ok_click)
        vbox.addWidget(self.ok_button)
        self.setLayout(vbox)

    def flash(self, bin_file: str, flash_device: CommDevice, device_name: Optional[str]) -> None:
        self.flash_thread = FlashThread(bin_file, flash_device, device_name)
        self.flash_thread.started.connect(self._flash_start)
        self.flash_thread.finished.connect(self.flash_thread.deleteLater)
        self.flash_thread.finished.connect(self._flash_stop)
        self.flash_thread.flash_done.connect(self._flash_done)
        self.flash_thread.flash_failed.connect(self._flash_failed)
        self.flash_thread.flash_progress.connect(self._flash_progress)

        self.flash_thread.start()
        self._flashing = True
        self.opened.emit()
        self.exec()

    def _flash_start(self) -> None:
        self.flash_label.setText("Flashing...")
        self.loading.show()
        self.ok_button.setHidden(True)
        self.flash_movie.start()

    def _flash_stop(self) -> None:
        self.flash_movie.stop()
        self.loading.hide()
        self._flashing = False

    def _flash_progress(self, progress: int) -> None:
        if self._flashing:
            self.flash_label.setText(f"Flashing... {progress}%")

    def _flash_done(self) -> None:
        self.flash_done.emit(True)
        self.flash_label.setText("Flashing done!")
        self.ok_button.setHidden(False)

    def _flash_failed(self, exception: Exception, traceback_str: Optional[str]) -> None:
        self.flash_done.emit(False)
        self.flash_label.setText("Flashing failed!")
        self.ok_button.setHidden(False)
        ExceptionWidget(self, exc=exception, traceback_str=traceback_str).exec()

    def _on_ok_click(self) -> None:
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._flashing:
            self.flash_thread.terminate()
            self.flash_thread.wait()
        super().closeEvent(event)


class FlashLoginDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.cookies: Optional[RequestsCookieJar] = None
        self.content: Optional[Tuple[bool, Session, Response]] = None
        self.logging_in = False
        self.cookies_accepted = False

        self.setWindowTitle("Acconeer developer login")
        self.setMinimumWidth(450)

        self.fetch_prompt = QTextEdit()
        self.fetch_prompt.setPlainText(BIN_FETCH_PROMPT)
        self.fetch_prompt.setReadOnly(True)

        self.usr_edit = QLineEdit()
        self.usr_edit.setPlaceholderText("<Enter email>")
        self.usr_edit.textChanged.connect(self._on_edit_credentials)

        self.pwd_edit = QLineEdit()
        self.pwd_edit.setPlaceholderText("<Enter password>")
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_edit.textChanged.connect(self._on_edit_credentials)

        self.login_status_label = QLabel()
        self.login_status_label.setHidden(True)

        self.remember_me_box = QCheckBox()
        self.remember_me_box.stateChanged.connect(self._on_remember_me_checked)
        self.remember_me_label = QLabel("Remember me")

        self.login_button = QPushButton("Login")
        self.login_button.setDisabled(True)
        self.login_button.clicked.connect(self._handle_login)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)

        self.login_spinner = QLabel()
        self.login_spinner.setHidden(True)

        loader_gif = None
        with as_file(files(resources) / "loader.gif") as path:
            loader_gif = path

        self.login_movie = QMovie(str(loader_gif))
        self.login_spinner.setMovie(self.login_movie)

        layout = QGridLayout(self)

        # fmt: off
        # Grid layout:                            row, col, rspan, cspan
        layout.addWidget(self.fetch_prompt,       0,   0,   1,     12)    # noqa: E241
        layout.addWidget(self.usr_edit,           1,   0,   1,     12)    # noqa: E241
        layout.addWidget(self.pwd_edit,           2,   0,   1,     12)    # noqa: E241
        layout.addWidget(self.remember_me_box,    3,   0,   1,     1)     # noqa: E241
        layout.addWidget(self.remember_me_label,  3,   1,   1,     11)    # noqa: E241
        layout.addWidget(self.login_status_label, 4,   0,   1,     12)    # noqa: E241
        layout.addWidget(self.login_button,       5,   0,   1,     6)     # noqa: E241
        layout.addWidget(self.login_spinner,      5,   6,   1,     3)     # noqa: E241
        layout.addWidget(self.cancel_button,      5,   9,   1,     3)     # noqa: E241
        # fmt: on

        self.setLayout(layout)

        self.usr_edit.setFocus()

    def _on_edit_credentials(self) -> None:
        if self.usr_edit.text() == "" or self.pwd_edit.text() == "":
            self.login_button.setEnabled(False)
        else:
            self.login_button.setEnabled(True)

    def _on_remember_me_checked(self) -> None:
        if self.remember_me_box.isChecked() and not self.cookies_accepted:
            cookie_dialog = CookieConsentDialog(self)
            cookie_dialog.exec()
            self.cookies_accepted = cookie_dialog.result() == QDialog.DialogCode.Accepted
            if not self.cookies_accepted:
                self.remember_me_box.setCheckState(Qt.CheckState.Unchecked)

    def _handle_login(self) -> None:
        self.login_status_label.setHidden(True)

        usr = self.usr_edit.text()
        pwd = self.pwd_edit.text()

        self.login_thread = AuthThread(usr, pwd, do_login=True)
        self.login_thread.started.connect(self._login_start)
        self.login_thread.finished.connect(self.login_thread.deleteLater)
        self.login_thread.finished.connect(self._login_stop)
        self.login_thread.auth_done.connect(self._login_done)
        self.login_thread.auth_failed.connect(self._login_failed)

        self.login_thread.start()
        self.logging_in = True

    def _login_start(self) -> None:
        self.setEnabled(False)
        self._show_login_progress()

    def _login_stop(self) -> None:
        self.logging_in = False
        self._hide_login_progress()
        self.setEnabled(True)

    def _login_done(
        self, auth_info: Tuple[RequestsCookieJar, Tuple[bool, Session, Response]]
    ) -> None:
        self.cookies, self.content = auth_info

        self.login_status_label.setHidden(True)

        if self.remember_me_box.isChecked():
            save_cookies(self.cookies)

        self.accept()

    def _login_failed(self) -> None:
        self.login_status_label.setText(_WRONG_CREDENTIALS_MSG)
        self.login_status_label.setHidden(False)

    def _show_login_progress(self) -> None:
        self.login_movie.start()
        self.login_spinner.setHidden(False)

    def _hide_login_progress(self) -> None:
        self.login_movie.stop()
        self.login_spinner.setHidden(True)

    def get_auth_info(
        self,
    ) -> Tuple[Optional[RequestsCookieJar], Optional[Tuple[bool, Session, Response]]]:
        return self.cookies, self.content

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.logging_in:
            self.login_thread.terminate()
            self.login_thread.wait()
        super().closeEvent(event)


class CookieConsentDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Cookie consent")

        layout = QGridLayout(self)

        self.consent_label = QLabel(
            "We use cookies to optimize the service of our applications", self
        )
        self.empty_row = QLabel("", self)

        self.cookie_policy_label = QLabel(
            "<a href='https://acconeer.com/cookie-policy-eu/'>Cookie Policy</a>", self
        )
        self.cookie_policy_label.setOpenExternalLinks(True)

        self.privacy_statement_label = QLabel(
            "<a href='https://developer.acconeer.com/privacy-policy/'>Privacy Statement</a>",
            self,
        )
        self.privacy_statement_label.setOpenExternalLinks(True)

        self.accept_button = QPushButton("Accept", self)
        self.accept_button.clicked.connect(self.accept)

        self.deny_button = QPushButton("Deny", self)
        self.deny_button.clicked.connect(self.reject)

        # fmt: off
        # Grid layout:                                 row, col, rspan, cspan
        layout.addWidget(self.consent_label,           0,   0,   1,     4)    # noqa: E241
        layout.addWidget(self.empty_row,               1,   0,   1,     4)    # noqa: E241
        layout.addWidget(self.cookie_policy_label,     2,   0,   1,     4)    # noqa: E241
        layout.addWidget(self.privacy_statement_label, 3,   0,   1,     4)    # noqa: E241
        layout.addWidget(self.accept_button,           4,   0,   1,     2)    # noqa: E241
        layout.addWidget(self.deny_button,             4,   2,   1,     2)    # noqa: E241
        # fmt: on

        self.setLayout(layout)


class LicenseAgreementDialog(QDialog):
    def __init__(self, license: DevLicense, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        layout = QGridLayout(self)

        self.license_text = QTextEdit(self)
        self.license_text.setReadOnly(True)

        self.accept_box = QCheckBox(self)
        self.accept_box.stateChanged.connect(self._on_accept_check)
        self.accept_label = QLabel("I understand the terms and conditions of the license", self)

        self.accept_button = QPushButton("Accept", self)
        self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self.accept)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)

        # fmt: off
        # Grid layout:                       row, col, rspan, cspan
        layout.addWidget(self.license_text,  0,   0,   10,    12)    # noqa: E241
        layout.addWidget(self.accept_box,    10,  0,   1,     1)     # noqa: E241
        layout.addWidget(self.accept_label,  10,  1,   1,     11)    # noqa: E241
        layout.addWidget(self.accept_button, 11,  0,   1,     6)     # noqa: E241
        layout.addWidget(self.cancel_button, 11,  6,   1,     6)     # noqa: E241
        # fmt: on

        self.setLayout(layout)

        self.set_license_text(license)

    def _on_accept_check(self) -> None:
        self.accept_button.setEnabled(self.accept_box.isChecked())

    def set_license_text(self, license: DevLicense) -> None:
        self.setWindowTitle(license.get_header())

        self.license_text.clear()
        self.license_text.insertHtml(license.get_subheader_element())

        content = license.get_content_elements()
        for paragraph in content:
            self.license_text.insertHtml(paragraph)
            self.license_text.insertHtml("<br><br>")

        self.license_text.moveCursor(QTextCursor.MoveOperation.Start)


class UserMessageDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: Optional[str],
        confirmation: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setMinimumWidth(450)
        self.setMinimumHeight(200)

        layout = QGridLayout(self)

        self.message_text = QTextEdit(self)
        self.message_text.setReadOnly(True)

        self.ok_button = QPushButton(confirmation, self)
        self.ok_button.setEnabled(True)
        self.ok_button.clicked.connect(self._on_ok)

        # fmt: off
        # Grid layout:                      row, col, rspan, cspan
        layout.addWidget(self.message_text, 0,   0,   4,     12)    # noqa: E241
        layout.addWidget(self.ok_button,    4,   0,   1,     2)     # noqa: E241
        # fmt: on

        self.setLayout(layout)

        self.setWindowTitle(title)
        if message is not None:
            self.set_message(message)

    def set_message(self, message: str) -> None:
        self.message_text.clear()
        self.message_text.insertHtml(message)
        self.message_text.moveCursor(QTextCursor.MoveOperation.Start)

    def _on_ok(self) -> None:
        self.accept()
