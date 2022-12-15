# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import importlib
import logging
import os
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, Tuple

import qtawesome as qta
from requests import Response, Session
from requests.cookies import RequestsCookieJar

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QMovie, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app import resources  # type: ignore[attr-defined]
from acconeer.exptool.app.new._enums import ConnectionInterface, ConnectionState
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui.misc import ExceptionWidget
from acconeer.exptool.flash import (  # type: ignore[import]
    BIN_FETCH_PROMPT,
    ET_DIR,
    DevLicense,
    clear_cookies,
    download,
    flash_image,
    get_content,
    get_cookies,
    get_flash_download_name,
    get_flash_known_devices,
    login,
    save_cookies,
)
from acconeer.exptool.utils import CommDevice  # type: ignore[import]

from .misc import BUTTON_ICON_COLOR, SerialPortComboBox, USBDeviceComboBox


_WRONG_CREDENTIALS_MSG = "<font color='red'>Incorrect username (email) or password</font>"

_LOGGED_IN_MSG = (
    "Logged in to <a href='https://developer.acconeer.com/'>developer.acconeer.com</a>"
)

log = logging.getLogger(__name__)


class _FlashThread(QThread):
    flash_failed = Signal(Exception, str)
    flash_done = Signal()
    flash_progress = Signal(int)

    def __init__(
        self, bin_file: str, flash_device: CommDevice, device_name: Optional[str]
    ) -> None:
        super().__init__()
        self.bin_file = bin_file
        self.flash_device = flash_device
        self.device_name = device_name

    def run(self) -> None:
        def progress_callback(progress: int, end: bool = False) -> None:
            if end:
                self.flash_progress.emit(100)
            else:
                self.flash_progress.emit(progress)

        try:
            flash_image(
                self.bin_file,
                self.flash_device,
                device_name=self.device_name,
                progress_callback=progress_callback,
            )
            self.flash_done.emit()
        except Exception as e:
            log.error(str(e))
            self.flash_failed.emit(HandledException(e), traceback.format_exc())


class _FlashDialog(QDialog):
    flash_done = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setWindowTitle("Flash tool")
        self.setMinimumWidth(250)

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignCenter)

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

        self.ok_button = QPushButton(self)
        self.ok_button.setText("OK")
        self.ok_button.setHidden(True)
        self.ok_button.clicked.connect(self._on_ok_click)
        vbox.addWidget(self.ok_button)
        self.setLayout(vbox)

    def flash(self, bin_file: str, flash_device: CommDevice, device_name: Optional[str]) -> None:
        self.flash_thread = _FlashThread(bin_file, flash_device, device_name)
        self.flash_thread.started.connect(self._flash_start)
        self.flash_thread.finished.connect(self.flash_thread.deleteLater)
        self.flash_thread.finished.connect(self._flash_stop)
        self.flash_thread.flash_done.connect(self._flash_done)
        self.flash_thread.flash_failed.connect(self._flash_failed)
        self.flash_thread.flash_progress.connect(self._flash_progress)

        self.flash_thread.start()
        self._flashing = True
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
        self.flash_done.emit()
        self.flash_label.setText("Flashing done!")
        self.ok_button.setHidden(False)

    def _flash_failed(self, exception: Exception, traceback_str: Optional[str]) -> None:
        self.flash_done.emit()
        self.flash_label.setText("Flashing failed!")
        ExceptionWidget(self, exc=exception, traceback_str=traceback_str).exec()
        self.ok_button.setHidden(False)

    def _on_ok_click(self) -> None:
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._flashing:
            self.flash_thread.terminate()
            self.flash_thread.wait()
        super().closeEvent(event)


class _FlashPopup(QDialog):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setWindowTitle("Flash tool")
        self.setMinimumWidth(550)

        self.bin_file: Optional[str] = None

        self.authenticating = False
        self.downloading_firmware = False
        self.dev_license = DevLicense()

        browse_button = QPushButton("Browse", self)
        browse_button.clicked.connect(self._browse_file)

        self.file_label = QLineEdit(self)
        self.file_label.setReadOnly(True)
        self.file_label.setEnabled(False)
        self.file_label.setPlaceholderText("<Select a bin file>")

        self.get_latest_button = QPushButton("Get latest bin file", self)
        self.get_latest_button.clicked.connect(self._get_latest_bin_file)

        self.downloaded_version_label = QLineEdit(self)
        self.downloaded_version_label.setReadOnly(True)
        self._reset_download_version()

        self.download_spinner = QLabel()
        self.download_spinner.setHidden(True)

        loader_gif = None
        with importlib.resources.path(resources, "loader.gif") as path:
            loader_gif = path

        self.download_movie = QMovie(str(loader_gif))
        self.download_spinner.setMovie(self.download_movie)

        self.download_status_label = QLabel()
        self.download_status_label.setHidden(True)

        self.interface_dd = QComboBox(self)
        self.interface_dd.addItem("Serial", userData=ConnectionInterface.SERIAL)
        self.interface_dd.addItem("USB", userData=ConnectionInterface.USB)

        self.interface_dd.currentIndexChanged.connect(self._on_interface_dd_change)

        self.device_selection = QComboBox(self)
        self.device_selection.setEnabled(False)
        self.device_name_selection = None
        self.device_selection.currentIndexChanged.connect(self._on_device_selection_change)

        self.stacked = QStackedWidget(self)
        self.stacked.setStyleSheet("QStackedWidget {background-color: transparent;}")
        self.stacked.addWidget(SerialPortComboBox(app_model, self.stacked))
        self.stacked.addWidget(USBDeviceComboBox(app_model, self.stacked))

        self.flash_button = QPushButton("Flash", self)
        self.flash_button.clicked.connect(self._flash)
        self.flash_button.setEnabled(False)

        self.logged_in_label = QLabel(self)
        self.logged_in_label.setOpenExternalLinks(True)

        self.logout_button = QPushButton("Logout", self)
        self.logout_button.clicked.connect(self._logout)
        self._hide_login_status()

        layout = QGridLayout(self)

        # fmt: off
        # Grid layout:                                  row, col, rspan, cspan
        layout.addWidget(browse_button,                 0,   0,   1,     3)    # noqa: E241
        layout.addWidget(self.file_label,               0,   3,   1,     9)    # noqa: E241
        layout.addWidget(self.get_latest_button,        1,   0,   1,     3)    # noqa: E241
        layout.addWidget(self.downloaded_version_label, 1,   3,   1,     9)    # noqa: E241
        layout.addWidget(self.interface_dd,             2,   0,   1,     3)    # noqa: E241
        layout.addWidget(self.stacked,                  2,   3,   1,     6)    # noqa: E241
        layout.addWidget(self.device_selection,         2,   9,   1,     3)    # noqa: E241
        layout.addWidget(self.flash_button,             3,   0,   1,    12)    # noqa: E241
        layout.addWidget(self.logged_in_label,          4,   0,   1,     8)    # noqa: E241
        layout.addWidget(self.logout_button,            4,   8,   1,     4)    # noqa: E241
        layout.addWidget(self.download_spinner,         5,   0,   1,     1)    # noqa: E241
        layout.addWidget(self.download_status_label,    5,   1,   1,    11)    # noqa: E241
        # fmt: on

        self.setLayout(layout)

        self.browse_file_dialog = QFileDialog(None)
        self.browse_file_dialog.setNameFilter("Bin files (*.bin)")

        self.flash_dialog = _FlashDialog(self)
        self.flash_dialog.flash_done.connect(self._flash_done)

        app_model.sig_notify.connect(self._on_app_model_update)

    @property
    def flash_device(self) -> Optional[CommDevice]:
        if self.app_model.connection_interface == ConnectionInterface.SERIAL:
            return self.app_model.serial_connection_device
        if self.app_model.connection_interface == ConnectionInterface.USB:
            return self.app_model.usb_connection_device
        return None

    @property
    def device_name(self) -> Optional[str]:
        if not self.device_selection.isEnabled():
            return None
        else:
            return self.device_name_selection

    def _get_latest_bin_file(self) -> None:
        self.auth_thread = _AuthThread(dev_license=self.dev_license)
        self.auth_thread.started.connect(self._auth_start)
        self.auth_thread.finished.connect(self.auth_thread.deleteLater)
        self.auth_thread.finished.connect(self._auth_stop)
        self.auth_thread.license_loaded.connect(self._license_loaded)
        self.auth_thread.auth_done.connect(self._auth_done)
        self.auth_thread.auth_failed.connect(self._auth_failed)

        self.authenticating = True
        self.auth_thread.start()

    def _auth_start(self) -> None:
        self._show_download_progress("Authenticating...")

    def _auth_stop(self) -> None:
        self._hide_download_progress()
        self.authenticating = False

    def _license_loaded(self, dev_license: DevLicense) -> None:
        self.dev_license = dev_license

    def _auth_done(
        self, auth_info: Tuple[RequestsCookieJar, Tuple[bool, Session, Response]]
    ) -> None:
        self._show_login_status(_LOGGED_IN_MSG)

        cookies, content = auth_info
        self._init_download(cookies, content)

    def _auth_failed(self) -> None:
        login_dialog = _FlashLoginDialog(self)
        authenticated = login_dialog.exec()

        if authenticated:
            self._show_login_status(_LOGGED_IN_MSG)
            cookies, content = login_dialog.get_auth_info()
            if cookies is not None and content is not None:
                self._init_download(cookies, content)

    def _init_download(
        self, cookies: RequestsCookieJar, content: Tuple[bool, Session, Response]
    ) -> None:

        license_agreement_dialog = LicenseAgreementDialog(self.dev_license, self)
        license_accepted = license_agreement_dialog.exec()
        device_download_name = get_flash_download_name(self.flash_device, self.device_name)

        if license_accepted:
            self.download_thread = BinDownloadThread(
                device_download_name, cookies, content[1], content[2]
            )

            self.download_thread.started.connect(self._download_start)
            self.download_thread.finished.connect(self.download_thread.deleteLater)
            self.download_thread.finished.connect(self._download_stop)
            self.download_thread.download_done.connect(self._download_done)
            self.download_thread.download_failed.connect(self._download_failed)

            self.downloading_firmware = True
            self.download_thread.start()

    def _download_start(self) -> None:
        self._show_download_progress("Downloading image file...")

    def _download_stop(self) -> None:
        self._hide_download_progress()
        self.downloading_firmware = False

    def _download_done(self, bin_file: str, version: str) -> None:
        self.bin_file = bin_file
        self._set_version(version)
        self.downloading_firmware = False
        self._draw()

    def _download_failed(self, error_msg: str) -> None:
        self.bin_file = None
        log.error(f"Failed to download firmware: {error_msg}")
        self._draw()

    def _browse_file(self) -> None:
        if self.browse_file_dialog.exec():
            filenames = self.browse_file_dialog.selectedFiles()
            self.bin_file = filenames[0]
            self._reset_download_version()

        self._draw()

    def _show_download_progress(self, text: str) -> None:
        self.download_movie.start()
        self.download_spinner.setHidden(False)
        self.download_status_label.setText(text)
        self.download_status_label.setHidden(False)

    def _hide_download_progress(self) -> None:
        self.download_movie.stop()
        self.download_spinner.setHidden(True)
        self.download_status_label.setHidden(True)
        self.adjustSize()

    def _flash(self) -> None:
        assert self.bin_file is not None

        self.app_model.set_port_updates_pause(True)
        self.flash_dialog.flash(self.bin_file, self.flash_device, self.device_name)

    def _flash_done(self) -> None:
        self.app_model.set_port_updates_pause(False)

    def _on_interface_dd_change(self) -> None:
        self.app_model.set_connection_interface(self.interface_dd.currentData())

    def _on_device_selection_change(self) -> None:
        self.device_name_selection = self.device_selection.currentText()

    def _on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.connection_interface in [ConnectionInterface.SERIAL, ConnectionInterface.USB]:
            interface_index = self.interface_dd.findData(app_model.connection_interface)
            if interface_index == -1:
                raise RuntimeError

            self.interface_dd.setCurrentIndex(interface_index)
            self.stacked.setCurrentIndex(interface_index)

            current_index = self.device_selection.currentIndex()
            if self.flash_device is None or (
                self.flash_device is not None and self.flash_device.name is not None
            ):
                self.device_selection.clear()
                self.device_selection.setEnabled(False)
            else:
                self.device_selection.clear()
                for dev in get_flash_known_devices():
                    self.device_selection.addItem(dev)
                self.device_selection.setEnabled(True)
                if current_index >= 0:
                    self.device_selection.setCurrentIndex(current_index)

            enable_select = not self.authenticating and not self.downloading_firmware
            self.get_latest_button.setEnabled(enable_select)
        else:
            self.device_selection.clear()
            self.device_selection.setEnabled(False)

        self._draw()

    def _draw(self) -> None:
        self.file_label.setText(self.bin_file if self.bin_file else "")
        self.file_label.setEnabled(self.bin_file is not None)
        self.flash_button.setEnabled(
            not self.authenticating
            and not self.downloading_firmware
            and self.flash_device is not None
            and self.bin_file is not None
        )

    def exec(self) -> None:
        if self.app_model.connection_interface == ConnectionInterface.SOCKET:
            self.app_model.set_connection_interface(ConnectionInterface.USB)

        super().exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.authenticating:
            self.auth_thread.terminate()
            self.auth_thread.wait()

        if self.downloading_firmware:
            self.download_thread.terminate()
            self.download_thread.wait()
        super().closeEvent(event)

    def _show_login_status(self, msg: str, disable_logout: bool = False) -> None:
        self.logged_in_label.setText(msg)
        self.logged_in_label.setHidden(False)
        self.logout_button.setHidden(False)
        self.logout_button.setEnabled(not disable_logout)

    def _hide_login_status(self) -> None:
        self.logged_in_label.setHidden(True)
        self.logout_button.setHidden(True)

    def _logout(self) -> None:
        clear_cookies()
        self._show_login_status("Currently not logged in", disable_logout=True)

    def _set_version(self, version: str) -> None:
        self.downloaded_version_label.setText(version)
        self.downloaded_version_label.setEnabled(True)

    def _reset_download_version(self) -> None:
        self.downloaded_version_label.setEnabled(False)
        self.downloaded_version_label.setText("<Downloaded bin file version>")


class FlashButton(QPushButton):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.setFixedWidth(100)
        self.setText("Flash")
        self.setIcon(qta.icon("mdi.flash", color=BUTTON_ICON_COLOR))
        self.setToolTip("Flash the device with a bin file")

        app_model.sig_notify.connect(self._on_app_model_update)
        self.pop_up = _FlashPopup(app_model, self)
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        self.pop_up.exec()

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.connection_state == ConnectionState.DISCONNECTED)


class _FlashLoginDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
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
        with importlib.resources.path(resources, "loader.gif") as path:
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
            self.cookies_accepted = CookieConsentDialog(self).exec()
            if not self.cookies_accepted:
                self.remember_me_box.setCheckState(Qt.Unchecked)

    def _handle_login(self) -> None:
        self.login_status_label.setHidden(True)

        usr = self.usr_edit.text()
        pwd = self.pwd_edit.text()

        self.login_thread = _AuthThread(usr, pwd, do_login=True)
        self.login_thread.started.connect(self._login_start)
        self.login_thread.finished.connect(self.login_thread.deleteLater)
        self.login_thread.finished.connect(self._login_stop)
        self.login_thread.auth_done.connect(self._login_done)
        self.login_thread.auth_failed.connect(self._login_failed)

        self.login_thread.start()
        self.logging_in = True

    def _login_start(self) -> None:
        self.login_button.setEnabled(False)
        self._show_login_progress()

    def _login_stop(self) -> None:
        self.logging_in = False
        self._hide_login_progress()
        self.login_button.setEnabled(True)

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
    ) -> (Tuple[Optional[RequestsCookieJar], Optional[Tuple[bool, Session, Response]]]):
        return self.cookies, self.content

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.logging_in:
            self.login_thread.terminate()
            self.login_thread.wait()
        super().closeEvent(event)


class _AuthThread(QThread):
    license_loaded = Signal(DevLicense)
    auth_failed = Signal()
    auth_done = Signal((RequestsCookieJar, Tuple[bool, Session, Response]))

    def __init__(
        self,
        usr: Optional[str] = "",
        pwd: Optional[str] = "",
        do_login: bool = False,
        dev_license: DevLicense = None,
    ) -> None:

        super().__init__()
        self.usr = usr
        self.pwd = pwd
        self.do_login = do_login
        self.dev_license = dev_license

    def run(self) -> None:
        login_succeeded = False

        if self.do_login:
            cookies = login(self.usr, self.pwd)
        else:
            cookies = get_cookies()

        try:
            if cookies is not None:
                content = get_content(cookies)
                login_succeeded = content[0]
            else:
                login_succeeded = False
        except Exception as e:
            log.error(str(e))

        if self.dev_license is not None:
            self.dev_license.load()
            self.license_loaded.emit(self.dev_license)

        if login_succeeded:
            self.auth_done.emit((cookies, content))
        else:
            if not self.do_login:
                clear_cookies()
            self.auth_failed.emit()


class BinDownloadThread(QThread):
    download_done = Signal(str, str)
    download_failed = Signal(str)

    def __init__(
        self,
        device: Optional[str],
        cookies: RequestsCookieJar,
        session: Session,
        response: Response,
    ) -> None:

        super().__init__()
        self.device = device
        self.cookies = cookies
        self.session = session
        self.response = response

    def run(self) -> None:

        if (
            self.device is None
            or self.cookies is None
            or self.session is None
            or self.response is None
        ):
            self.download_failed.emit("Failed to start download")
        else:
            with TemporaryDirectory() as temp_dir:
                try:
                    temp_file, version = download(
                        session=self.session,
                        cookies=self.cookies,
                        path=temp_dir,
                        device=self.device,
                    )

                    if temp_file is not None:
                        bin_file = str(ET_DIR / Path(temp_file).name)
                        os.replace(temp_file, bin_file)
                        self.download_done.emit(bin_file, version)
                    else:
                        self.download_failed.emit(
                            f"Failed to download firmware for device {self.device}"
                        )
                except Exception as e:
                    self.download_failed.emit(str(e))
                finally:
                    self.session.close()


class LicenseAgreementDialog(QDialog):
    def __init__(self, license: DevLicense, parent: QWidget) -> None:
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

        self._set_license_text(license)

    def _on_accept_check(self) -> None:
        self.accept_button.setEnabled(self.accept_box.isChecked())

    def _set_license_text(self, license: DevLicense) -> None:
        self.setWindowTitle(license.get_header())

        self.license_text.insertHtml(license.get_subheader_element())

        content = license.get_content_elements()
        for paragraph in content:
            self.license_text.insertHtml(paragraph)
            self.license_text.insertHtml("<br><br>")

        self.license_text.moveCursor(QTextCursor.MoveOperation.Start)


class CookieConsentDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
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
