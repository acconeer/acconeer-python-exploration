# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import typing as t

import pytest

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QDialog

from acconeer.exptool._artifact_repository import _dev_site_repository
from acconeer.exptool.app.new.ui.components.devsite import LicenseDialog, LoginDialog
from acconeer.exptool.app.new.ui.components.devsite.license import LicenseWidget


if t.TYPE_CHECKING:
    from tests.app.conftest import FakeDevSite


pytestmark = pytest.mark.usefixtures("qapplication")


def _finish_background_tasks() -> None:
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()


def _start_login(dialog: LoginDialog, password: str, remember_me: bool = False) -> None:
    dialog.show()
    dialog.login_widget.email_line_edit.setText("jane@example.com")
    dialog.login_widget.password_line_edit.setText(password)
    dialog.login_widget.remember_me_checkbox.setChecked(remember_me)
    dialog.login_widget.login_button.click()


def test_login_dialog_accepts_with_a_ready_session(fake_devsite: FakeDevSite) -> None:
    dialog = LoginDialog()

    _start_login(dialog, fake_devsite.PASSWORD)
    _finish_background_tasks()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.repository is not None
    assert dialog.repository.has_logged_in_previously()


def test_cancelled_login_dialog_hands_back_no_session(fake_devsite: FakeDevSite) -> None:
    dialog = LoginDialog()
    dialog.show()

    dialog.reject()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.repository is None


def test_login_finishing_after_cancel_is_ignored(fake_devsite: FakeDevSite) -> None:
    dialog = LoginDialog()

    _start_login(dialog, fake_devsite.PASSWORD)
    dialog.reject()
    _finish_background_tasks()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.repository is None


def test_remembered_login_is_saved(fake_devsite: FakeDevSite) -> None:
    dialog = LoginDialog()

    _start_login(dialog, fake_devsite.PASSWORD, remember_me=True)
    _finish_background_tasks()

    assert _dev_site_repository.COOKIE_FILEPATH.exists()


def test_login_cancelled_in_flight_is_still_remembered(fake_devsite: FakeDevSite) -> None:
    dialog = LoginDialog()

    _start_login(dialog, fake_devsite.PASSWORD, remember_me=True)
    dialog.reject()
    _finish_background_tasks()

    assert _dev_site_repository.COOKIE_FILEPATH.exists()


@pytest.fixture
def license_dialog(monkeypatch: pytest.MonkeyPatch) -> LicenseDialog:
    monkeypatch.setattr(
        LicenseWidget,
        "_get_dev_license",
        staticmethod(lambda: ("Fetched license title", "subtitle", "paragraphs")),
    )
    return LicenseDialog()


def test_license_cannot_be_accepted_before_it_is_shown(license_dialog: LicenseDialog) -> None:
    assert not license_dialog._accept_button.isEnabled()

    _finish_background_tasks()

    assert license_dialog._accept_button.isEnabled()


def test_license_dialog_title_follows_the_license(license_dialog: LicenseDialog) -> None:
    _finish_background_tasks()

    assert license_dialog.windowTitle() == "Fetched license title"
