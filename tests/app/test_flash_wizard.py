# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from PySide6.QtWidgets import QApplication

from acconeer.exptool._artifact_repository import LoginRequiredError
from acconeer.exptool.app.new.ui.flash_tab.widgets import (
    DownloadPage,
    FlashWizard,
    LicensePage,
    WizardField,
    _Page,
)


@pytest.fixture(autouse=True, scope="module")
def qapplication() -> QApplication:
    return QApplication.instance() or QApplication()


@pytest.fixture
def wizard(monkeypatch: pytest.MonkeyPatch) -> FlashWizard:
    # LicensePage fetches the real dev license over the network as soon as
    # it's constructed, which FlashWizard.__init__ does unconditionally.
    monkeypatch.setattr(
        LicensePage, "get_dev_licence", staticmethod(lambda: ("title", "subtitle", "paragraphs"))
    )

    w = FlashWizard(app_model=None)  # type: ignore[arg-type]
    w.artifact_repository = MagicMock()
    # A page's "visible" field only reflects reality once the wizard is
    # actually shown; a page not on screen stays invisible regardless of
    # what gets written to the field.
    w.show()
    w.restart()
    w.setCurrentId(_Page.DOWNLOAD)
    return w


def test_stale_login_during_download_routes_back_to_login_page(wizard: FlashWizard) -> None:
    download_page = wizard.currentPage()
    assert isinstance(download_page, DownloadPage)

    download_page.handle_exception_during_download(LoginRequiredError("Login has expired"))

    wizard.artifact_repository.forget_login.assert_called_once()
    assert wizard.currentId() == _Page.LOGIN
    assert wizard.field(WizardField.LOGIN_FEEDBACK_VISIBLE) is True
