# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from importlib.resources import as_file, files
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
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool._core.communication.comm_devices import CommDevice
from acconeer.exptool.app import resources
from acconeer.exptool.app.new._enums import ConnectionInterface, ConnectionState
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui import utils as ui_utils
from acconeer.exptool.app.new.ui.device_comboboxes import SerialPortComboBox, USBDeviceComboBox
from acconeer.exptool.flash import (
    DevLicense,
    clear_cookies,
    get_flash_download_name,
    get_flash_known_devices,
)
from acconeer.exptool.flash._products import (
    EVK_TO_PRODUCT_MAP,
    PRODUCT_NAME_TO_FLASH_MAP,
)

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
        self._auth_info: Optional[Tuple[RequestsCookieJar, Tuple[bool, Session, Response]]] = None

        self.authenticating = False
        self.downloading_firmware = False
        self.dev_license = DevLicense()

        browse_button = QPushButton("Browse", self)
        browse_button.clicked.connect(self._browse_file)

        self.file_label = QLineEdit(self)
        self.file_label.setReadOnly(True)
        self._reset_file_label()

        self._get_latest_button = QPushButton("Get latest bin file", self)
        self._get_latest_button.clicked.connect(self._get_latest_bin_file)

        self.downloaded_version_label = QLineEdit(self)
        self.downloaded_version_label.setReadOnly(True)
        self.downloaded_version_label.setMinimumWidth(175)
        self._reset_download_version()

        self.download_spinner = QLabel()
        self.download_spinner.setHidden(True)

        loader_gif = None
        with as_file(files(resources) / "loader.gif") as path:
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
        self._device_post_dfu_description = None
        self.device_selection.currentIndexChanged.connect(self._on_device_selection_change)

        self._device_widget = QStackedWidget(self)
        self._device_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self._device_widget.setStyleSheet("QStackedWidget {background-color: transparent;}")
        self._device_widget.addWidget(SerialPortComboBox(app_model, self._device_widget))
        self._device_widget.addWidget(USBDeviceComboBox(app_model, self._device_widget))

        self.flash_button = QPushButton("Flash", self)
        self.flash_button.clicked.connect(self._flash)
        self.flash_button.setEnabled(False)

        self.clear_cookies_button = QPushButton("Clear cookies", self)
        self.clear_cookies_button.clicked.connect(self._clear_cookies)

        self._flash_dialog = FlashDialog()
        self._flash_dialog.flash_done.connect(self._flash_done)
        self._flash_dialog.setHidden(True)
        self._flash_dialog.opened.connect(self._flash_opened)
        self._flash_dialog.finished.connect(self._flash_finished)

        browse_layout = QGridLayout()

        # fmt: off
        # Grid layout:                                       row, col, rspan, cspan
        browse_layout.addWidget(browse_button,                 0,   0,   1,     3)    # noqa: E241
        browse_layout.addWidget(self.file_label,               0,   3,   1,     9)    # noqa: E241
        # fmt: on

        get_latest_layout = QGridLayout()

        # fmt: off
        # Grid layout:                                           row, col, rspan, cspan
        get_latest_layout.addWidget(self._get_latest_button,       0,   0,   1,     3)    # noqa: E241
        get_latest_layout.addWidget(self.downloaded_version_label, 0,   3,   1,     9)    # noqa: E241
        get_latest_layout.addWidget(self.clear_cookies_button,     1,   8,   1,     4)    # noqa: E241
        get_latest_layout.addWidget(self.download_spinner,         2,   0,   1,     1)    # noqa: E241
        get_latest_layout.addWidget(self.download_status_label,    2,   1,   1,    11)    # noqa: E241
        # fmt: on

        flash_layout = QGridLayout()

        # fmt: off
        # Grid layout:                                      row, col, rspan, cspan
        flash_layout.addWidget(self.interface_dd,             0,   0,   1,     3)    # noqa: E241
        flash_layout.addWidget(self._device_widget,           0,   3,   1,     6)    # noqa: E241
        flash_layout.addWidget(self.device_selection,         0,   9,   1,     3)    # noqa: E241
        flash_layout.addWidget(self.flash_button,             1,   0,   1,    12)    # noqa: E241
        flash_layout.addWidget(self._flash_dialog,            2,   0,   1,    12)    # noqa: E241
        # fmt: on

        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(ui_utils.LayoutWrapper(browse_layout), "Browse")
        self._tab_widget.addTab(ui_utils.LayoutWrapper(get_latest_layout), "Get latest binary")

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._tab_widget)
        main_layout.addWidget(ui_utils.LayoutWrapper(flash_layout))

        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        main_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(main_widget)

        self.setLayout(layout)

        self._browse_file_dialog = QFileDialog()
        self._browse_file_dialog.setNameFilter("Bin files (*.bin)")
        self._browse_file_dialog.accepted.connect(self._browse_file_accepted)
        self._browse_file_dialog.finished.connect(self._browse_file_finised)

        self._login_dialog = FlashLoginDialog()
        self._login_dialog.accepted.connect(self._login_accept)
        self._login_dialog.rejected.connect(self._login_rejected)

        self._license_agreement_dialog = LicenseAgreementDialog(self.dev_license)
        self._license_agreement_dialog.accepted.connect(self._license_accepted)
        self._license_agreement_dialog.rejected.connect(self._license_rejected)

        self._user_msg_dialog = UserMessageDialog(
            "Bootloader description",
            None,
            "Got it! The board is in bootloader mode",
        )
        self._user_msg_dialog.finished.connect(self._user_msg_dialog_finished)

        self._post_flash_dialog = UserMessageDialog(
            "Finalize flashing description",
            None,
            "OK",
        )
        self._post_flash_dialog.finished.connect(self._post_flash_dialog_finished)

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
        return self.device_name_selection

    def _license_accepted(self) -> None:
        assert self.flash_device is not None
        device_download_name = get_flash_download_name(self.flash_device, self.device_name)

        assert self._auth_info is not None
        cookies, content = self._auth_info

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

    def _license_rejected(self) -> None:
        self.setEnabled(True)

    def _login_accept(self) -> None:
        (cookies, content) = self._login_dialog.get_auth_info()
        if cookies is not None and content is not None:
            self._init_download((cookies, content))

    def _login_rejected(self) -> None:
        self.setEnabled(True)

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
        self.setEnabled(False)
        self._show_download_progress("Authenticating...")

    def _auth_stop(self) -> None:
        self._hide_download_progress()
        self.authenticating = False

    def _license_loaded(self, dev_license: DevLicense) -> None:
        self.dev_license = dev_license
        self._license_agreement_dialog.set_license_text(self.dev_license)

    def _auth_done(
        self, auth_info: Tuple[RequestsCookieJar, Tuple[bool, Session, Response]]
    ) -> None:
        self._init_download(auth_info)

    def _auth_failed(self) -> None:
        self._login_dialog.open()

    def _init_download(
        self, auth_info: Tuple[RequestsCookieJar, Tuple[bool, Session, Response]]
    ) -> None:
        self.setEnabled(False)
        self._auth_info = auth_info
        self._license_agreement_dialog.open()

    def _download_start(self) -> None:
        self._show_download_progress("Downloading image file...")

    def _download_stop(self) -> None:
        self._hide_download_progress()
        self.downloading_firmware = False
        self.setEnabled(True)

    def _download_done(self, bin_file: str, version: str) -> None:
        self.bin_file = bin_file
        self._set_version(version)
        self.downloading_firmware = False
        self._reset_file_label()
        self._draw()

    def _download_failed(self, error_msg: str) -> None:
        self.bin_file = None
        log.error(f"Failed to download firmware: {error_msg}")
        self._reset_file_label()
        self._draw()

    def _browse_file_accepted(self) -> None:
        filenames = self._browse_file_dialog.selectedFiles()
        self.bin_file = filenames[0]
        self._reset_download_version()
        self.file_label.setText(self.bin_file if self.bin_file else "")
        self.file_label.setEnabled(self.bin_file is not None)

    def _browse_file_finised(self) -> None:
        self.setEnabled(True)
        self._draw()

    def _browse_file(self) -> None:
        self.setEnabled(False)
        self._browse_file_dialog.open()

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

    def _user_msg_dialog_finished(self) -> None:
        assert self.bin_file is not None
        assert self.flash_device is not None
        self.app_model.set_port_updates_pause(True)
        self._flash_dialog.flash(self.bin_file, self.flash_device, self.device_name)

    def _post_flash_dialog_finished(self) -> None:
        self.app_model.set_port_updates_pause(False)

    def _flash(self) -> None:
        assert self.bin_file is not None
        assert self.flash_device is not None

        if self.app_model.connection_state is not ConnectionState.DISCONNECTED:
            retcode = QMessageBox.warning(
                self,
                "Sensor Connected",
                "Exploration Tool is connected to a sensor that needs to be disconnect before flashing.\n\nDisconnect the sensor?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            user_accepted = retcode & QMessageBox.StandardButton.Yes > 0
            if user_accepted:
                self.app_model.disconnect_client()
                _ = QMessageBox.information(
                    self,
                    "Sensor Disconnecting ...",
                    "Disconnecting the sensor. Press the <b>Flash</b> button again.",
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok,
                )
            return

        boot_description = self._get_boot_description(self.flash_device, self.device_name)
        self._device_post_dfu_description = self._get_post_dfu_description(
            self.flash_device, self.device_name
        )
        if boot_description:
            self._user_msg_dialog.set_message(boot_description)
            self._user_msg_dialog.open()
        else:
            self.app_model.set_port_updates_pause(True)
            self._flash_dialog.flash(self.bin_file, self.flash_device, self.device_name)

    def _flash_opened(self) -> None:
        self._tab_widget.setEnabled(False)
        self.interface_dd.setEnabled(False)
        self._device_widget.setEnabled(False)
        self.device_selection.setEnabled(False)
        self.flash_button.setEnabled(False)

    def _flash_finished(self) -> None:
        self._tab_widget.setEnabled(True)
        self.interface_dd.setEnabled(True)
        self._device_widget.setEnabled(True)
        self.device_selection.setEnabled(True)
        self.flash_button.setEnabled(True)

    def _flash_done(self, flashing_ok: bool) -> None:
        if flashing_ok and self._device_post_dfu_description is not None:
            self._post_flash_dialog.set_message(self._device_post_dfu_description)
            self._post_flash_dialog.open()
        else:
            self.app_model.set_port_updates_pause(False)

    def _on_interface_dd_change(self) -> None:
        self.app_model.set_connection_interface(self.interface_dd.currentData())
        self._draw()

    def _on_device_selection_change(self) -> None:
        self.device_name_selection = self.device_selection.currentText()
        self._draw()

    def _on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.connection_interface in [ConnectionInterface.SERIAL, ConnectionInterface.USB]:
            interface_index = self.interface_dd.findData(app_model.connection_interface)
            if interface_index == -1:
                raise RuntimeError

            self.interface_dd.setCurrentIndex(interface_index)
            self._device_widget.setCurrentIndex(interface_index)

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
            self._get_latest_button.setEnabled(enable_select)
        else:
            self.device_selection.clear()
            self.device_selection.setEnabled(False)

        self._draw()

    def _draw(self) -> None:
        self.flash_button.setEnabled(
            not self.authenticating
            and not self.downloading_firmware
            and self.flash_device is not None
            and self.bin_file is not None
        )
        self._get_latest_button.setEnabled(
            (self.flash_device is not None and self.flash_device.name is not None)
            or (self.device_name is not None and len(self.device_name) > 0)
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.authenticating:
            self.auth_thread.terminate()
            self.auth_thread.wait()

        if self.downloading_firmware:
            self.download_thread.terminate()
            self.download_thread.wait()
        super().closeEvent(event)

    def _clear_cookies(self) -> None:
        clear_cookies()

    def _set_version(self, version: str) -> None:
        self.downloaded_version_label.setText(version)
        self.downloaded_version_label.setEnabled(True)

    def _reset_download_version(self) -> None:
        self.downloaded_version_label.setEnabled(False)
        self.downloaded_version_label.setText("<Downloaded bin file version>")

    def _reset_file_label(self) -> None:
        self.file_label.setText("<Select a bin file>")
        self.file_label.setEnabled(False)

    def _get_boot_description(self, flash_device: CommDevice, device_name: Optional[str]) -> Any:
        flash_device_name: Optional[str] = device_name or flash_device.name
        product: Optional[str] = None

        if flash_device_name in EVK_TO_PRODUCT_MAP:
            product = EVK_TO_PRODUCT_MAP[flash_device_name]

        if product in PRODUCT_NAME_TO_FLASH_MAP:
            return PRODUCT_NAME_TO_FLASH_MAP[product].get_boot_description(product)

        return None

    def _get_post_dfu_description(
        self, flash_device: CommDevice, device_name: Optional[str]
    ) -> Any:
        flash_device_name: Optional[str] = device_name or flash_device.name
        product: Optional[str] = None

        if flash_device_name in EVK_TO_PRODUCT_MAP:
            product = EVK_TO_PRODUCT_MAP[flash_device_name]

        if product in PRODUCT_NAME_TO_FLASH_MAP:
            return PRODUCT_NAME_TO_FLASH_MAP[product].get_post_dfu_description(product)

        return None
