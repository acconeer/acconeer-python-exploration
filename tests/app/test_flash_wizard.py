# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import threading
import typing as t

import pytest
import requests

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from acconeer.exptool._artifact_repository import DevSiteRepository, LoginRequiredError
from acconeer.exptool._core.communication.comm_devices import USBDevice
from acconeer.exptool.app.new.ui.components.devsite.license import LicenseWidget
from acconeer.exptool.app.new.ui.components.devsite.login import LoginFormWidget
from acconeer.exptool.app.new.ui.flash_tab.widgets import (
    DeviceSelectionPage,
    DownloadPage,
    FlashWizard,
    LoginFormPage,
    _Page,
)
from acconeer.exptool.app.new.ui.utils import FeedbackStyleSheet


if t.TYPE_CHECKING:
    from tests.app.conftest import FakeDevSite


pytestmark = pytest.mark.usefixtures("qapplication")


@pytest.fixture
def wizard(monkeypatch: pytest.MonkeyPatch, fake_devsite: FakeDevSite) -> FlashWizard:
    # LicenseWidget fetches the real dev license over the network as soon as
    # it's constructed, which FlashWizard.__init__ does unconditionally.
    monkeypatch.setattr(
        LicenseWidget,
        "_get_dev_license",
        staticmethod(lambda: ("title", "subtitle", "paragraphs")),
    )

    w = FlashWizard(app_model=None)  # type: ignore[arg-type]
    # A page's "visible" field only reflects reality once the wizard is
    # actually shown; a page not on screen stays invisible regardless of
    # what gets written to the field.
    w.show()
    w.restart()
    w.setCurrentId(_Page.DOWNLOAD)
    return w


def _start_login(wizard: FlashWizard, password: str) -> LoginFormPage:
    wizard.setCurrentId(_Page.LOGIN)
    login_page = wizard.currentPage()
    assert isinstance(login_page, LoginFormPage)

    login_page.login_widget.email_line_edit.setText("jane@example.com")
    login_page.login_widget.password_line_edit.setText(password)
    login_page.login_widget.login_button.click()
    return login_page


def _wait_for_background_tasks() -> None:
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()


def _log_in(wizard: FlashWizard, password: str) -> LoginFormPage:
    login_page = _start_login(wizard, password)
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()
    return login_page


def test_stale_login_during_download_routes_back_to_login_page(
    wizard: FlashWizard, fake_devsite: FakeDevSite
) -> None:
    wizard.artifact_repository.cookies = fake_devsite.logged_in_cookies()
    download_page = wizard.currentPage()
    assert isinstance(download_page, DownloadPage)

    download_page.handle_exception_during_download(LoginRequiredError("Login has expired"))

    assert not wizard.artifact_repository.has_logged_in_previously()
    assert wizard.currentId() == _Page.LOGIN
    login_page = wizard.currentPage()
    assert isinstance(login_page, LoginFormPage)
    assert login_page.login_widget.feedback_lbl.isVisible()
    assert "login has expired" in login_page.login_widget.feedback_lbl.text()


def test_successful_login_hands_session_to_wizard_and_advances(
    wizard: FlashWizard, fake_devsite: FakeDevSite
) -> None:
    _log_in(wizard, fake_devsite.PASSWORD)

    assert wizard.artifact_repository.has_logged_in_previously()
    assert wizard.currentId() == _Page.DOWNLOAD


def test_wrong_password_shows_error_feedback(wizard: FlashWizard) -> None:
    login_page = _log_in(wizard, "wrong password")

    feedback_lbl = login_page.login_widget.feedback_lbl
    assert "Wrong email or password" in feedback_lbl.text()
    assert feedback_lbl.styleSheet() == FeedbackStyleSheet.ERROR
    assert wizard.currentId() == _Page.LOGIN


def test_unreachable_devsite_during_login_shows_connection_error(
    wizard: FlashWizard, fake_devsite: FakeDevSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_connection_error(*_: object, **__: object) -> None:
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(DevSiteRepository, "login", raise_connection_error)

    login_page = _log_in(wizard, fake_devsite.PASSWORD)

    feedback_lbl = login_page.login_widget.feedback_lbl
    assert "internet connection" in feedback_lbl.text()
    assert feedback_lbl.styleSheet() == FeedbackStyleSheet.ERROR
    assert wizard.currentId() == _Page.LOGIN


def test_login_page_is_incomplete_after_forget_me(
    wizard: FlashWizard, fake_devsite: FakeDevSite
) -> None:
    login_page = _log_in(wizard, fake_devsite.PASSWORD)

    download_page = wizard.page(_Page.DOWNLOAD)
    assert isinstance(download_page, DownloadPage)
    download_page.forget_me()

    assert not login_page.isComplete()


def test_login_button_stops_claiming_a_login_after_forget_me(
    wizard: FlashWizard, fake_devsite: FakeDevSite
) -> None:
    login_page = _log_in(wizard, fake_devsite.PASSWORD)

    download_page = wizard.page(_Page.DOWNLOAD)
    assert isinstance(download_page, DownloadPage)
    download_page.forget_me()

    assert (
        login_page.login_widget.login_button.text() == LoginFormWidget._LOGIN_BUTTON_DEFAULT_TEXT
    )


def test_successful_login_clears_earlier_error_feedback(
    wizard: FlashWizard, fake_devsite: FakeDevSite
) -> None:
    _log_in(wizard, "wrong password")
    login_page = _log_in(wizard, fake_devsite.PASSWORD)

    feedback_lbl = login_page.login_widget.feedback_lbl
    assert feedback_lbl.text() == LoginFormWidget._FEEDBACK_DEFAULT_TEXT
    assert feedback_lbl.styleSheet() == FeedbackStyleSheet.NICE


@pytest.fixture
def held_login(
    monkeypatch: pytest.MonkeyPatch, fake_devsite: FakeDevSite
) -> t.Iterator[threading.Event]:
    """Holds every login until the returned event is set, then lets it succeed."""
    release = threading.Event()

    def login(repository: DevSiteRepository, *_: object, **__: object) -> None:
        release.wait()
        repository.cookies = fake_devsite.logged_in_cookies()

    monkeypatch.setattr(DevSiteRepository, "login", login)
    yield release
    release.set()
    _wait_for_background_tasks()


def test_editing_the_form_during_a_login_keeps_the_button_disabled(
    wizard: FlashWizard, held_login: threading.Event
) -> None:
    login_page = _start_login(wizard, "a password")

    login_page.login_widget.password_line_edit.setText("another password")

    assert not login_page.login_widget.login_button.isEnabled()


def test_revisiting_the_login_page_during_a_login_keeps_the_pending_text(
    wizard: FlashWizard, held_login: threading.Event
) -> None:
    login_page = _start_login(wizard, "a password")

    login_page.login_widget.hide()
    login_page.login_widget.show()

    assert (
        login_page.login_widget.login_button.text() == LoginFormWidget._LOGIN_BUTTON_PENDING_TEXT
    )


def test_login_finishing_after_leaving_the_login_page_keeps_the_wizard_still(
    wizard: FlashWizard, held_login: threading.Event
) -> None:
    _wait_for_background_tasks()
    wizard.setCurrentId(_Page.LICENSE)
    wizard.next()
    login_page = wizard.currentPage()
    assert isinstance(login_page, LoginFormPage)
    login_page.login_widget.email_line_edit.setText("jane@example.com")
    login_page.login_widget.password_line_edit.setText("a password")
    login_page.login_widget.login_button.click()
    wizard.back()
    page_after_back = wizard.currentId()
    assert page_after_back != _Page.LOGIN

    held_login.set()
    _wait_for_background_tasks()

    assert wizard.currentId() == page_after_back


def test_device_page_skips_a_device_the_flasher_does_not_know(wizard: FlashWizard) -> None:
    device_page = wizard.page(_Page.DEVICE_SELECTION)
    assert isinstance(device_page, DeviceSelectionPage)
    device = USBDevice(name="XC211", vid=0xACC0, pid=0xE211, recognized=True)

    assert not device_page.is_currently_selected_module(device)


def test_license_page_takes_the_title_of_the_fetched_license(wizard: FlashWizard) -> None:
    _wait_for_background_tasks()

    assert wizard.page(_Page.LICENSE).title() == "title"


def test_license_page_is_incomplete_after_a_failed_fetch(
    monkeypatch: pytest.MonkeyPatch, fake_devsite: FakeDevSite
) -> None:
    def raise_connection_error() -> tuple[str, str, str]:
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(LicenseWidget, "_get_dev_license", staticmethod(raise_connection_error))
    w = FlashWizard(app_model=None)  # type: ignore[arg-type]
    _wait_for_background_tasks()

    assert not w.page(_Page.LICENSE).isComplete()
