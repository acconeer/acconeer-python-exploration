# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import pytest
import requests

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from acconeer.exptool.app.new.ui.components.devsite.license import LicenseWidget


pytestmark = pytest.mark.usefixtures("qapplication")


def _raise_connection_error() -> tuple[str, str, str]:
    raise requests.exceptions.ConnectionError


def test_license_fetch_without_internet_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LicenseWidget, "_get_dev_license", staticmethod(_raise_connection_error))

    widget = LicenseWidget()
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()

    assert "internet connection" in widget.license_text_edit.toPlainText()


def _return_a_license() -> tuple[str, str, str]:
    return ("title", "subtitle", "paragraphs")


def test_license_fetch_can_be_retried_after_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LicenseWidget, "_get_dev_license", staticmethod(_raise_connection_error))
    widget = LicenseWidget()
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()

    monkeypatch.setattr(LicenseWidget, "_get_dev_license", staticmethod(_return_a_license))
    widget.retry_button.click()
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()

    assert widget.has_license()
    assert "paragraphs" in widget.license_text_edit.toPlainText()
