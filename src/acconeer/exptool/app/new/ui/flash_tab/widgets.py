# Copyright (c) Acconeer AB, 2025
# All rights reserved
from __future__ import annotations

import importlib.resources
import typing as t
from dataclasses import dataclass
from enum import Enum, IntEnum, auto

import requests

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimerEvent, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from acconeer.exptool._core.communication.comm_devices import CommDevice
from acconeer.exptool.app.new.app import ConnectionState
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.storage import get_temp_dir
from acconeer.exptool.app.new.ui import icons
from acconeer.exptool.flash import (
    DevLicense,
    clear_cookies,
    download,
    flash_image,
    get_boot_description,
    get_content,
    get_cookies,
    get_flash_download_name,
    get_flash_known_devices,
    get_post_dfu_description,
    is_fw_downloadable,
    login,
    save_cookies,
)
from acconeer.exptool.flash._dev_license import DEV_LICENSE_DEFAULT_HEADER
from acconeer.exptool.flash._products import EVK_TO_PRODUCT_MAP

from . import resources
from .dialogs import UserMessageDialog


DEVSITE_REGISTER_URL = "https://developer.acconeer.com/register/"


class WizardField(str, Enum):
    DOWNLOAD_SELECTED = "download_selected"
    MODULE = "module"

    EMAIL = "email"
    PASSWORD = "password"
    REMEMBER_ME = "remember_me"
    LOGIN_FEEDBACK = "login_feedback"
    LOGIN_FEEDBACK_VISIBLE = "login_feedback_visible"
    LOGIN_FEEDBACK_STYLESHEET = "login_feedback_stylesheet"

    BIN_PATH = "bin_path"

    def required(self) -> str:
        return self + "*"


class FeedbackStyleSheet(str, Enum):
    ERROR = f"background-color: {icons.ERROR_RED}; color: white"
    NICE = f"background-color: {icons.BUTTON_ICON_COLOR}; color: white"


class ModuleSelectionPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        self.setTitle("Select module to flash")

        with importlib.resources.path(resources, "xe125.jpg") as path:
            assert path.exists()
            self.xe125_pixmap = QPixmap(path)

        with importlib.resources.path(resources, "xe121.jpg") as path:
            assert path.exists()
            self.xe121_pixmap = QPixmap(path)

        with importlib.resources.path(resources, "xm126.jpg") as path:
            assert path.exists()
            self.xm126_pixmap = QPixmap(path)

        self.picture_label = QLabel("Picture")

        combo_box = QComboBox()
        combo_box.currentTextChanged.connect(self.switch_to_matching_pixmap)

        for supported_module_name in get_flash_known_devices():
            combo_box.addItem(supported_module_name)

        self.registerField(WizardField.MODULE, combo_box, "currentText", "currentTextChanged")

        layout = QFormLayout()
        layout.addRow("Module", combo_box)
        layout.addRow(self.picture_label)
        self.setLayout(layout)

    def switch_to_matching_pixmap(self, combo_box_text: str) -> None:
        if combo_box_text == "XC120":
            self.picture_label.setPixmap(self.xe121_pixmap)
        elif combo_box_text == "XM125":
            self.picture_label.setPixmap(self.xe125_pixmap)
        elif combo_box_text == "XM126":
            self.picture_label.setPixmap(self.xm126_pixmap)
        else:
            pass


class DeviceSelectionPage(QWizardPage):
    _TITLE_FMT = "Select a connected {} to flash"

    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.app_model = app_model
        self.setTitle(self._TITLE_FMT.format("device"))

        self.device_cb = QComboBox()
        self.device_cb.currentTextChanged.connect(self.update_wizards_comm_device)
        self.device_cb.currentTextChanged.connect(lambda _: self.completeChanged.emit())

        refresh_button = QPushButton()
        refresh_button.setIcon(icons.REFRESH())
        refresh_button.clicked.connect(self._repopulate_combobox)

        self.show_all_devices_checkbox = QCheckBox("Show all devices")
        self.show_all_devices_checkbox.setChecked(False)
        self.show_all_devices_checkbox.toggled.connect(self._repopulate_combobox)

        self.feedback_lbl = QLabel("")
        self.feedback_lbl.setWordWrap(True)
        self.feedback_lbl.setStyleSheet(f"background-color: {icons.WARNING_YELLOW}; color: white")
        self.feedback_lbl.setVisible(False)

        cb_refresh_layout = QHBoxLayout()
        cb_refresh_layout.addWidget(self.device_cb, stretch=1)
        cb_refresh_layout.addWidget(refresh_button, stretch=0)

        layout = QFormLayout()
        layout.addRow("Selected device", cb_refresh_layout)
        layout.addRow(self.show_all_devices_checkbox)
        layout.addRow(self.feedback_lbl)
        layout.addRow(_Spacer())
        self.setLayout(layout)

    def isComplete(self) -> bool:
        w = self.wizard()
        assert isinstance(w, FlashWizard)
        return w.comm_device is not None

    def update_wizards_comm_device(self) -> None:
        w = self.wizard()
        assert isinstance(w, FlashWizard)
        w.set_comm_device(self.device_cb.currentData())

    def initializePage(self) -> None:
        self._repopulate_combobox()
        self.setTitle(self._TITLE_FMT.format(self.field(WizardField.MODULE)))

    def cleanupPage(self) -> None:
        self.show_all_devices_checkbox.setChecked(False)

    def is_currently_selected_module(self, comm_device: CommDevice) -> bool:
        if comm_device.name is None:
            return False

        evk_name = comm_device.name
        product_name = EVK_TO_PRODUCT_MAP[evk_name]
        return bool(self.field(WizardField.MODULE) == product_name)

    def _repopulate_combobox(self) -> None:
        self.device_cb.clear()
        comm_devices = [
            dev
            for dev in (
                self.app_model.available_usb_devices + self.app_model.available_serial_devices
            )
            if (self.is_currently_selected_module(dev) and dev.recognized)
            or self.show_all_devices_checkbox.isChecked()
        ]
        for device in comm_devices:
            self.device_cb.addItem(device.display_name(), device)

        if self.device_cb.count() == 0:
            self.feedback_lbl.setText(
                "<br>".join(
                    [
                        f"No <b>{self.field(WizardField.MODULE)}</b> can be recognized.",
                        "Is your module properly plugged in to this computer?",
                        "Try reinserting USB cable and the clicking the Refresh Button above."
                        "As a last resort, check <i>Show all devices</i> and look for your device there.",
                    ]
                )
            )
            self.feedback_lbl.setVisible(True)
        else:
            self.feedback_lbl.setVisible(False)


class SelectLocalFileOrDownloadFromDevsitePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        self.setTitle("Application binary source")

        self._download_btn = QRadioButton("Automatically download from developer.acconeer.com")
        self._download_btn.setChecked(True)
        self.registerField(WizardField.DOWNLOAD_SELECTED, self._download_btn, "checked", "toggled")

        self._local_file_btn = QRadioButton("Local file")

        button_group = QButtonGroup(parent=self)
        button_group.addButton(self._download_btn)
        button_group.addButton(self._local_file_btn)

        layout = QVBoxLayout()
        layout.addWidget(self._download_btn)
        layout.addWidget(self._local_file_btn)
        self.setLayout(layout)

    def initializePage(self) -> None:
        if is_fw_downloadable(self.field(WizardField.MODULE)):
            self._download_btn.setEnabled(True)
            self._download_btn.setChecked(True)
        else:
            self._download_btn.setEnabled(False)
            self._local_file_btn.setChecked(True)


class BrowseLocalFilePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        # The state management gets weird if going back to here from the FlashPage.
        # Making this a "commit page" makes it impossible to go back here
        # (and the user needs to cancel the wizard instead)
        self.setCommitPage(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, "Next")

        self.path_label = QLineEdit()
        self.path_label.setReadOnly(True)
        self.path_label.setPlaceholderText("Path to local file")

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._select_local_file)

        layout = QHBoxLayout()
        layout.addWidget(self.path_label, stretch=1)
        layout.addWidget(browse_btn, stretch=0)
        self.setLayout(layout)

    def _select_local_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            caption="caption", filter="Bin files (*.bin *.image)"
        )
        self.path_label.setText(filename)
        self.setField(WizardField.BIN_PATH, filename)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return len(self.field(WizardField.BIN_PATH)) > 0

    def initializePage(self) -> None:
        self.setTitle(f"Browse for local binary to flash your {self.field('module')} with")


class LoginFormPage(QWizardPage):
    _LOGIN_BUTTON_DEFAULT_TEXT = "Log in"
    _LOGIN_BUTTON_PENDING_TEXT = "Logging in ..."

    _COOKIE_POLICY_LINK = "<a href='https://acconeer.com/cookie-policy-eu/'>Cookie Policy</a>"
    _PRIVACY_STATEMENT_LINK = (
        "<a href='https://developer.acconeer.com/privacy-policy/'>Privacy Statement</a>"
    )
    _REMEMBER_ME_TERMS_HTML = (
        "<i>"
        + (
            "<br>".join(
                [
                    '"Remember me" will save your credentials for next time.',
                    "By checking the box you agree to",
                    f"Acconeer's {_COOKIE_POLICY_LINK} and {_PRIVACY_STATEMENT_LINK}.",
                ]
            )
        )
        + "</i>"
    )

    def __init__(self) -> None:
        super().__init__()
        self.feedback_lbl = QLineEdit("Log in using your developer.accconeer.com account below")
        self.feedback_lbl.setReadOnly(True)
        self.feedback_lbl.setVisible(True)
        self.feedback_lbl.setStyleSheet(FeedbackStyleSheet.NICE)

        self.registerField(WizardField.LOGIN_FEEDBACK, self.feedback_lbl, "text")
        self.registerField(WizardField.LOGIN_FEEDBACK_VISIBLE, self.feedback_lbl, "visible")
        self.registerField(WizardField.LOGIN_FEEDBACK_STYLESHEET, self.feedback_lbl, "styleSheet")

        self.email_line_edit = QLineEdit()
        self.email_line_edit.setPlaceholderText("example@domain.com")
        self.registerField(WizardField.EMAIL.required(), self.email_line_edit)
        self.email_line_edit.textChanged.connect(self.update_login_button_enabledness)

        self.password_line_edit = QLineEdit()
        self.password_line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_line_edit.setPlaceholderText("*" * 12)
        self.registerField(WizardField.PASSWORD.required(), self.password_line_edit)
        self.password_line_edit.textChanged.connect(self.update_login_button_enabledness)

        self.peek_button = QToolButton()
        self.peek_button.setIcon(icons.EYE_OPEN())
        self.peek_button.setCheckable(True)
        self.peek_button.setChecked(False)
        self.peek_button.toggled.connect(self._handle_peek_state_change)

        password_and_peek_layout = QHBoxLayout()
        password_and_peek_layout.addWidget(self.password_line_edit)
        password_and_peek_layout.addWidget(self.peek_button)

        remember_me_checkbox = QCheckBox()
        remember_me_checkbox.setText("Remember me")
        remember_me_checkbox.setChecked(False)
        remember_me_terms_label = QLabel(self._REMEMBER_ME_TERMS_HTML)
        remember_me_terms_label.setStyleSheet(f"QLabel {{ color: {icons.TEXT_LIGHTGREY}; }}")
        self.registerField(WizardField.REMEMBER_ME, remember_me_checkbox)

        self.register_btn = QPushButton(
            "Don't have an account? Register on developer.acconeer.com!"
        )
        self.register_btn.setIcon(icons.EXTERNAL_LINK())
        self.register_btn.clicked.connect(lambda: QDesktopServices.openUrl(DEVSITE_REGISTER_URL))

        self.login_button = QPushButton(self._LOGIN_BUTTON_DEFAULT_TEXT)
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self.put_login_bg_task)

        layout = QFormLayout()

        layout.addRow(self.feedback_lbl)
        layout.addRow("Email", self.email_line_edit)
        layout.addRow("Password", password_and_peek_layout)
        layout.addRow(remember_me_checkbox, remember_me_terms_label)

        layout.addRow(self.login_button)

        layout.addRow(_Spacer())
        layout.addRow(self.register_btn)

        self.setLayout(layout)

    def update_login_button_enabledness(self) -> None:
        should_be_enabled = (
            self.field(WizardField.EMAIL) != "" and self.field(WizardField.PASSWORD) != ""
        )
        self.login_button.setEnabled(should_be_enabled)

    def put_login_bg_task(self) -> None:
        email = self.field(WizardField.EMAIL)
        pwd = self.field(WizardField.PASSWORD)
        self.login_button.setText(self._LOGIN_BUTTON_PENDING_TEXT)
        self.login_button.setEnabled(False)
        BGTask.create_task(
            login,
            args=(email, pwd),
            return_cb=self.handle_login_return,
            exception_cb=self.handle_login_exception,
        )

    def handle_login_exception(self, exception: Exception) -> None:
        self.login_button.setText(self._LOGIN_BUTTON_DEFAULT_TEXT)
        self.login_button.setEnabled(True)

        error_msg = get_internet_related_error_message(exception)

        self.setField(WizardField.LOGIN_FEEDBACK, error_msg)
        self.setField(WizardField.LOGIN_FEEDBACK_VISIBLE, True)
        self.setField(WizardField.LOGIN_FEEDBACK_STYLESHEET, FeedbackStyleSheet.ERROR)
        self.login_button.setText(self._LOGIN_BUTTON_DEFAULT_TEXT)

    def handle_login_return(self, cookies: requests.cookies.CookieJar) -> None:
        self.login_button.setEnabled(True)

        if cookies is None:
            login_success = False
            session = None
        else:
            (login_success, session, _) = get_content(cookies)

        if login_success:
            obf_email = try_get_obfuscated_email_from_cookiejar(cookiejar=cookies)
            if obf_email is None:
                self.login_button.setText("Logged in")
            else:
                self.login_button.setText(f"Logged in as {obf_email}")

            w = self.wizard()
            assert isinstance(w, FlashWizard)
            w.set_cookies(cookies)
            w.set_session(session)
            self.completeChanged.emit()
            w.next()  # Go to next page automatically
        else:
            self.setField(WizardField.LOGIN_FEEDBACK, "Wrong email or password. Please try again.")
            self.setField(WizardField.LOGIN_FEEDBACK_VISIBLE, True)
            self.setField(WizardField.LOGIN_FEEDBACK_STYLESHEET, FeedbackStyleSheet.ERROR)
            self.login_button.setText(self._LOGIN_BUTTON_DEFAULT_TEXT)

    def _handle_peek_state_change(self, peek_checked: bool) -> None:
        if peek_checked:
            self.password_line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.peek_button.setIcon(icons.EYE_CLOSED())
        else:
            self.password_line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.peek_button.setIcon(icons.EYE_OPEN())

    def isComplete(self) -> bool:
        w = self.wizard()
        assert isinstance(w, FlashWizard)
        return w.cookies is not None

    def validatePage(self) -> bool:
        if self.field(WizardField.REMEMBER_ME):
            w = self.wizard()
            assert isinstance(w, FlashWizard)
            save_cookies(w.cookies)

        return True


class LicensePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        self.license_has_been_fetched = False

        self.setTitle(DEV_LICENSE_DEFAULT_HEADER)
        self.setButtonText(QWizard.WizardButton.NextButton, "I Accept")

        self.license_text_edit = QTextEdit()
        self.license_text_edit.setReadOnly(True)
        self.license_text_edit.setText("Downloading license ...")
        BGTask.create_task(self.get_dev_licence, args=(), return_cb=self.populate_devlicence)

        layout = QVBoxLayout()
        layout.addWidget(self.license_text_edit)
        self.setLayout(layout)

    def isComplete(self) -> bool:
        return self.license_has_been_fetched

    @staticmethod
    def get_dev_licence() -> tuple[str, str, str]:
        dev_license = DevLicense()
        dev_license.load()

        title = dev_license.get_header()
        subtitle = dev_license.get_subheader_element()
        paragraphs = "".join(dev_license.get_content_elements())

        return (title, subtitle, paragraphs)

    def populate_devlicence(self, t: tuple[str, str, str]) -> None:
        self.license_has_been_fetched = True
        self.completeChanged.emit()

        (title, subtitle, paragraphs) = t
        self.setTitle(title)
        self.license_text_edit.setHtml(subtitle + paragraphs)


class DownloadPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        self.setTitle("Download")

        # The flow is weird if going back to download from e.g. flash page.
        # Making this a "commit page" makes it impossible to go back here
        # (and the user needs to cancel the wizard instead)
        self.setCommitPage(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, "Next")

        self._download_button = _ThreeDotAnimatedQPushButton("Download")
        self._download_button.clicked.connect(self.start_download)

        self.feedback_lbl = QLineEdit("")
        self.feedback_lbl.setReadOnly(True)
        self.feedback_lbl.setVisible(False)
        self.feedback_lbl.setStyleSheet(FeedbackStyleSheet.ERROR)

        self._auth_lbl = QLabel("")

        self._forget_me_btn = QPushButton("Forget me")
        self._forget_me_btn.setFlat(True)
        self._forget_me_btn.clicked.connect(self.forget_me)

        layout = QGridLayout()
        layout.addWidget(self._download_button, 0, 0, 1, 2)
        layout.addWidget(self.feedback_lbl, 1, 0, 1, 2)
        layout.addWidget(_Spacer(), 2, 0, 1, 2)
        layout.addWidget(self._auth_lbl, 3, 0, 1, 1)
        layout.addWidget(self._forget_me_btn, 3, 1, 1, 1)

        self.setLayout(layout)

    def initializePage(self) -> None:
        self._download_button.setText(f"Download image for {self.field(WizardField.MODULE)}")
        self._download_button.setEnabled(True)

        w = self.wizard()
        assert isinstance(w, FlashWizard)
        cookies = w.cookies

        if cookies is None:
            self._forget_me_btn.setVisible(False)
        else:
            self._forget_me_btn.setVisible(True)
            mby_obf_email = try_get_obfuscated_email_from_cookiejar(cookies)
            if mby_obf_email is None:
                self._auth_lbl.setText("Logged in.")
            else:
                self._auth_lbl.setText(f"Logged in as {mby_obf_email}")

    def isComplete(self) -> bool:
        return len(self.field(WizardField.BIN_PATH)) > 0

    def forget_me(self) -> None:
        clear_cookies()
        w = self.wizard()
        assert isinstance(w, FlashWizard)
        w.cookies = None
        w.setCurrentId(_Page.LOGIN)

    def start_download(self) -> None:
        self._download_button.setEnabled(False)
        self._download_button.set_text_with_dots_animation("Downloading")

        try:
            w = self.wizard()
            assert isinstance(w, FlashWizard)
            cookies = w.cookies
            session = w.session
            comm_device = w.comm_device

            if cookies is None or comm_device is None:
                # Something has gone wrong, ask user to retry
                w.setCurrentId(_Page.OOPSIE)
                return

            if session is None:
                (login_success, session, _) = get_content(cookies)
                w.session = session
                if not login_success:
                    self.setField(
                        WizardField.LOGIN_FEEDBACK, "Cookies have gone stale, Please login again"
                    )
                    self.setField(WizardField.LOGIN_FEEDBACK_VISIBLE, True)
                    self.setField(WizardField.LOGIN_FEEDBACK_STYLESHEET, FeedbackStyleSheet.NICE)
                    clear_cookies()
                    w.cookies = None
                    w.setCurrentId(_Page.LOGIN)
                    return

            device = get_flash_download_name(
                comm_device,
                device_name=self.field(WizardField.MODULE),
            )
            download_dir_path = get_temp_dir()

            BGTask.create_task(
                download,
                (session, cookies, download_dir_path, device),
                return_cb=self.handle_successful_download,
                exception_cb=self.handle_exception_during_download,
            )
        except Exception:
            self.wizard().setCurrentId(_Page.OOPSIE)

    def handle_successful_download(self, bin_path_and_version: tuple[str, str]) -> None:
        self._download_button.setEnabled(False)

        (bin_path, version) = bin_path_and_version
        self.setField(WizardField.BIN_PATH, bin_path)
        self._download_button.setText(f"Downloaded {version}")
        self.completeChanged.emit()
        self.wizard().next()  # automatically go to next page

    def handle_exception_during_download(self, exception: Exception) -> None:
        self._download_button.setEnabled(True)
        self._download_button.setText("Download")

        self.feedback_lbl.setVisible(True)
        error_msg = get_internet_related_error_message(exception)
        self.feedback_lbl.setText(error_msg)


class FlashPage(QWizardPage):
    def __init__(
        self,
        app_model: AppModel,
    ) -> None:
        super().__init__()

        self.setTitle("Flash")

        self.app_model = app_model
        self.flash_completed_successfully = False

        bin_path_line_edit = QLineEdit()
        bin_path_line_edit.setReadOnly(True)
        self.registerField(WizardField.BIN_PATH.required(), bin_path_line_edit)

        self.feedback_lbl = QLineEdit()
        self.feedback_lbl.setReadOnly(True)
        self.feedback_lbl.setVisible(False)
        self.feedback_lbl.setStyleSheet(f"background-color: {icons.ERROR_RED}; color: white")

        self._flash_button = _ThreeDotAnimatedQPushButton("Flash")
        self._flash_button.clicked.connect(self.flash)

        layout = QFormLayout()
        layout.addRow("Binary path", bin_path_line_edit)
        layout.addRow(self._flash_button)
        layout.addRow(self.feedback_lbl)
        layout.addRow(_Spacer())
        self.setLayout(layout)

    def isComplete(self) -> bool:
        return self.flash_completed_successfully

    def flash(self) -> None:
        if self.app_model.connection_state is not ConnectionState.DISCONNECTED:
            retcode = QMessageBox.warning(
                self,
                "Sensor Connected",
                "Exploration Tool is connected to a sensor that needs to be disconnect before flashing.\n\nDisconnect the sensor?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            user_accepted = (retcode & QMessageBox.StandardButton.Yes) > 0
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

        w = self.wizard()
        assert isinstance(w, FlashWizard)
        comm_device = w.comm_device

        if comm_device is None:
            w.setCurrentId(_Page.OOPSIE)
            return

        boot_description = get_boot_description(comm_device, self.field(WizardField.MODULE))
        if boot_description is not None:
            dialog = UserMessageDialog(
                "Bootloader description",
                boot_description,
                "Got it! The board is in bootloader mode",
            )
            diagcode = dialog.exec()
            if diagcode == QDialog.DialogCode.Rejected:
                return

        self._flash_button.set_text_with_dots_animation("Flashing")
        self._flash_button.setEnabled(False)
        self.app_model.port_updater_enable(False)

        BGTask.create_task(
            flash_image,
            args=(self.field(WizardField.BIN_PATH), comm_device),
            return_cb=self.handle_flash_return,
            exception_cb=self.handle_flash_exception,
        )

    def handle_flash_return(self, _: t.Any) -> None:
        self.flash_completed_successfully = True
        self.completeChanged.emit()

        self._flash_button.setText("Flashed!")
        self._flash_button.setEnabled(False)

        self.feedback_lbl.setVisible(False)
        self.app_model.port_updater_enable(True)

        w = self.wizard()
        assert isinstance(w, FlashWizard)
        comm_device = w.comm_device

        if comm_device is None:
            w.setCurrentId(_Page.OOPSIE)
            return

        post_dfu_description = get_post_dfu_description(
            comm_device, self.field(WizardField.MODULE)
        )
        if post_dfu_description is not None:
            dialog = UserMessageDialog(
                "Bootloader description",
                post_dfu_description,
                "Done",
            )
            dialog.exec()

        self.wizard().next()  # automatically go to next page

    def handle_flash_exception(self, exception: Exception) -> None:
        self._flash_button.setText("Flash")
        self._flash_button.setEnabled(True)

        self.feedback_lbl.setVisible(True)
        self.feedback_lbl.setText("Flash failed. Please try again.")

        self.app_model.port_updater_enable(True)


class FinalPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        self.setTitle("All done!")

        help_text = "\n".join(
            [
                "If you run into any issues directly after flashing your module,",
                "try removing its power and plugging it back in again.",
            ]
        )

        layout = QVBoxLayout()
        layout.addWidget(QLabel(help_text))
        self.setLayout(layout)


class OopsiePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()

        self.setTitle("Error")

        github_et_issues_url = "https://github.com/acconeer/acconeer-python-exploration/issues"
        github_et_issues_link = (
            f"<a href='{github_et_issues_url}'>Exploration Tool's GitHub Issues</a>"
        )
        help_text = "<br><br>".join(
            [
                "<b>An unforseen error has occured!</b>",
                "Please restart the flashing process from the beginning.",
                "Use a reliable internet connection if applicable and available.",
                f"If all else fails, please get in touch with us at {github_et_issues_link}",
            ]
        )
        label = QLabel(help_text)
        label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)


class _Page(IntEnum):
    MODULE_SELECTION = auto()
    DEVICE_SELECTION = auto()
    LOCAL_FILE_OR_DOWNLOAD = auto()
    BROWSE_LOCAL_FILE = auto()
    LICENSE = auto()
    LOGIN = auto()
    DOWNLOAD = auto()
    FLASH = auto()
    FINAL = auto()
    OOPSIE = auto()


class FlashWizard(QWizard):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.setWindowTitle("Flash Wizard")

        self.comm_device: t.Optional[CommDevice] = None
        self.cookies: t.Optional[requests.cookies.CookieJar] = get_cookies()
        self.session: t.Optional[requests.Session] = None

        self.setPage(_Page.MODULE_SELECTION, ModuleSelectionPage())
        self.setPage(_Page.DEVICE_SELECTION, DeviceSelectionPage(app_model))
        self.setPage(_Page.LOCAL_FILE_OR_DOWNLOAD, SelectLocalFileOrDownloadFromDevsitePage())
        self.setPage(_Page.BROWSE_LOCAL_FILE, BrowseLocalFilePage())
        self.setPage(_Page.LICENSE, LicensePage())
        self.setPage(_Page.LOGIN, LoginFormPage())
        self.setPage(_Page.DOWNLOAD, DownloadPage())
        self.setPage(_Page.FLASH, FlashPage(app_model))
        self.setPage(_Page.FINAL, FinalPage())

        self.setPage(_Page.OOPSIE, OopsiePage())

    def set_comm_device(self, comm_device: CommDevice) -> None:
        self.comm_device = comm_device

    def set_cookies(self, cookies: requests.cookies.CookieJar) -> None:
        self.cookies = cookies

    def set_session(self, session: requests.Session) -> None:
        self.session = session

    def nextId(self) -> int:
        if self.cookies is None:
            license_next_page = _Page.LOGIN
        else:
            license_next_page = _Page.DOWNLOAD

        if self.field(WizardField.DOWNLOAD_SELECTED):
            local_file_or_download_next_page = _Page.LICENSE
        else:
            local_file_or_download_next_page = _Page.BROWSE_LOCAL_FILE

        transitions: dict[int, int] = {
            _Page.MODULE_SELECTION: _Page.DEVICE_SELECTION,
            _Page.DEVICE_SELECTION: _Page.LOCAL_FILE_OR_DOWNLOAD,
            _Page.LOCAL_FILE_OR_DOWNLOAD: local_file_or_download_next_page,
            _Page.LICENSE: license_next_page,
            _Page.LOGIN: _Page.DOWNLOAD,
            _Page.DOWNLOAD: _Page.FLASH,
            _Page.BROWSE_LOCAL_FILE: _Page.FLASH,
            _Page.FLASH: _Page.FINAL,
            _Page.FINAL: -1,
            _Page.OOPSIE: -1,
        }
        return transitions[self.currentId()]


_T = t.TypeVar("_T")


@dataclass
class _AnimationState:
    timer_id: int
    text_stem: str
    frame_no: int

    def increment_frame_no(self) -> None:
        self.frame_no += 1

    def text_to_display(self) -> str:
        dots = "." + ("." * (self.frame_no % 3))
        return self.text_stem + " " + dots.ljust(3)


class _ThreeDotAnimatedQPushButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._state: t.Optional[_AnimationState] = None

    def setText(self, text: str) -> None:
        self._internal_set_text(text)

        if self._state is None:
            return

        self.killTimer(self._state.timer_id)
        self._state = None

    def _internal_set_text(self, text: str) -> None:
        super().setText(text)

    def set_text_with_dots_animation(self, text: str) -> None:
        self._state = _AnimationState(
            timer_id=self.startTimer(1000),
            text_stem=text,
            frame_no=0,
        )
        self._internal_set_text(self._state.text_to_display())

    def timerEvent(self, ev: QTimerEvent) -> None:
        if self._state is None:
            return

        btn_text = self._state.text_to_display()
        self._state.increment_frame_no()

        self._internal_set_text(btn_text)


def reraise(e: Exception) -> None:
    raise e


class BGTask(QRunnable):
    class Signals(QObject):
        sig_return = Signal(object)  # _T
        sig_exception = Signal(Exception)

    @classmethod
    def create_task(
        cls,
        f: t.Callable[..., _T],
        args: tuple[t.Any, ...],
        return_cb: t.Callable[[_T], t.Any] = lambda _: None,
        exception_cb: t.Callable[[Exception], t.Any] = reraise,
    ) -> None:
        signals = BGTask.Signals()
        signals.sig_return.connect(return_cb)
        signals.sig_exception.connect(exception_cb)

        QThreadPool.globalInstance().start(BGTask(f, args, signals))

    def __init__(self, f: t.Callable[..., _T], args: tuple[t.Any, ...], signals: Signals) -> None:
        super().__init__()
        self.signals = signals
        self.f = f
        self.args = args

    def run(self) -> None:
        try:
            res = self.f(*self.args)
        except Exception as e:
            self.signals.sig_exception.emit(e)
        else:
            self.signals.sig_return.emit(res)


def get_internet_related_error_message(exception: Exception) -> str:
    if isinstance(exception, requests.exceptions.ConnectionError):
        # there is no internet access
        error_msg = "Could not reach the Developer Site. Do you have an internet connection?"
    else:
        error_msg = "An unexpected error occured:\n" + "".join(exception.args)
    return error_msg


def try_get_obfuscated_email_from_cookiejar(
    cookiejar: t.Optional[requests.cookies.CookieJar],
) -> t.Optional[str]:
    # A cookie in the cookiejar k,v pairs look like this (2025-08-19):
    # k = wordpress_logged_in_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    # v = firstname-lastnamedomain-com%XXXXXXXXXXXXXXXXXXXXXXXXX...
    # (yes, the "@" is stripped)
    if cookiejar is None:
        return None

    try:
        for k, v in cookiejar.items():
            if "logged_in" in k:
                (mangled_email, *_) = str(v).split("%")
                if mangled_email.count("-") < 2:
                    return (
                        mangled_email[0]
                        + "@".center(len(mangled_email) - 2, "*")
                        + mangled_email[-1]
                    )
                else:
                    leftmost_dash_idx = mangled_email.find("-")
                    rightmost_dash_idx = mangled_email.rfind("-")
                    return (
                        mangled_email[:leftmost_dash_idx]
                        + "@".center(rightmost_dash_idx - leftmost_dash_idx, "*")
                        + mangled_email[rightmost_dash_idx + 1 :]
                    )
    except Exception:
        return None

    return None


class _Spacer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
