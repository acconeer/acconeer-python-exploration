# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import importlib
import logging
from typing import Any, Optional, Tuple

from requests import Response, Session
from requests.cookies import RequestsCookieJar

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QMovie
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app import resources  # type: ignore[attr-defined]
from acconeer.exptool.app.new._enums import ConnectionInterface
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui import utils as ui_utils
from acconeer.exptool.app.new.ui.device_comboboxes import SerialPortComboBox, USBDeviceComboBox
from acconeer.exptool.app.new.ui.plugin_components.utils import GroupBox
from acconeer.exptool.flash import (  # type: ignore[import]
    DevLicense,
    clear_cookies,
    get_flash_download_name,
    get_flash_known_devices,
)
from acconeer.exptool.flash._products import (  # type: ignore[import]
    EVK_TO_PRODUCT_MAP,
    PRODUCT_NAME_TO_FLASH_MAP,
)
from acconeer.exptool.utils import CommDevice, SerialDevice  # type: ignore[import]

from .dialogs import FlashDialog, FlashLoginDialog, LicenseAgreementDialog, UserMessageDialog
from .threads import AuthThread, BinDownloadThread


_LOGGED_IN_MSG = (
    "Logged in to <a href='https://developer.acconeer.com/'>developer.acconeer.com</a>"
)
log = logging.getLogger(__name__)


class FlashMainWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(type(self).__name__)
        self.setStyleSheet(f"*#{type(self).__name__} " + "{ background-color: #11515766; }")

        self.app_model = app_model

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

        button_layout = QGridLayout()

        # fmt: off
        # Grid layout:                                  row, col, rspan, cspan
        button_layout.addWidget(browse_button,                 0,   0,   1,     3)    # noqa: E241
        button_layout.addWidget(self.file_label,               0,   3,   1,     9)    # noqa: E241
        button_layout.addWidget(self.get_latest_button,        1,   0,   1,     3)    # noqa: E241
        button_layout.addWidget(self.downloaded_version_label, 1,   3,   1,     9)    # noqa: E241
        button_layout.addWidget(self.interface_dd,             2,   0,   1,     3)    # noqa: E241
        button_layout.addWidget(self.stacked,                  2,   3,   1,     6)    # noqa: E241
        button_layout.addWidget(self.device_selection,         2,   9,   1,     3)    # noqa: E241
        button_layout.addWidget(self.flash_button,             3,   0,   1,    12)    # noqa: E241
        button_layout.addWidget(self.logged_in_label,          4,   0,   1,     8)    # noqa: E241
        button_layout.addWidget(self.logout_button,            4,   8,   1,     4)    # noqa: E241
        button_layout.addWidget(self.download_spinner,         5,   0,   1,     1)    # noqa: E241
        button_layout.addWidget(self.download_status_label,    5,   1,   1,    11)    # noqa: E241
        # fmt: on

        box = GroupBox.vertical("", parent=self)
        box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        box.layout().addWidget(ui_utils.LayoutWrapper(button_layout))

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(box)

        self.setLayout(layout)

        self.browse_file_dialog = QFileDialog(None)
        self.browse_file_dialog.setNameFilter("Bin files (*.bin)")

        self.flash_dialog = FlashDialog(self)
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
        self.auth_thread = AuthThread(dev_license=self.dev_license)
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
        login_dialog = FlashLoginDialog(self)
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

        boot_description = self._get_boot_description(self.flash_device, self.device_name)
        if boot_description:
            UserMessageDialog(
                "Bootloader description",
                boot_description,
                "Got it! The board is in bootloader mode",
                self,
            ).exec()

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

    def _get_boot_description(self, flash_device: SerialDevice, device_name: Optional[str]) -> Any:

        flash_device_name: str = device_name or flash_device.name
        product: Optional[str] = None

        if flash_device_name in EVK_TO_PRODUCT_MAP.keys():
            product = EVK_TO_PRODUCT_MAP[flash_device_name]

        if product in PRODUCT_NAME_TO_FLASH_MAP.keys():
            return PRODUCT_NAME_TO_FLASH_MAP[product].get_boot_description(product)

        return None
