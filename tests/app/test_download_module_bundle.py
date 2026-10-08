# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import importlib
import typing as t

import pytest
import requests

from PySide6.QtWidgets import QDialog

from acconeer.exptool._artifact_repository import LoginRequiredError


# The package re-exports a function by the module's name, hiding the module
download_module = importlib.import_module(
    "acconeer.exptool.app.new.ui.components.devsite.download_module_bundle"
)


class _SavedLogin:
    def has_logged_in_previously(self) -> bool:
        return True

    def forget_login(self) -> None:
        pass


class _AcceptedDialog:
    def __init__(self, *_: t.Any) -> None:
        pass

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


class _LoginWidget:
    def __init__(self) -> None:
        self.feedback: list[str] = []

    def set_feedback(self, message: str, _style: t.Any) -> None:
        self.feedback.append(message)


class _CancelledLoginDialog:
    shown: list[_CancelledLoginDialog] = []

    def __init__(self, *_: t.Any) -> None:
        self.login_widget = _LoginWidget()
        self.repository = None
        _CancelledLoginDialog.shown.append(self)

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Rejected


class _FailingDownloadDialog:
    error: Exception
    downloaded_path = None

    def __init__(self, *_: t.Any) -> None:
        pass

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Rejected


@pytest.fixture
def critical_messages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(
        download_module.DevSiteRepository, "from_saved_login", staticmethod(_SavedLogin)
    )
    monkeypatch.setattr(download_module, "LicenseDialog", _AcceptedDialog)
    monkeypatch.setattr(download_module, "LoginDialog", _CancelledLoginDialog)
    monkeypatch.setattr(download_module, "_DownloadDialog", _FailingDownloadDialog)
    monkeypatch.setattr(
        download_module.QMessageBox,
        "critical",
        staticmethod(lambda _parent, _title, text: messages.append(text)),
    )
    _CancelledLoginDialog.shown = []
    return messages


def test_offline_download_failure_suggests_checking_the_connection(
    monkeypatch: pytest.MonkeyPatch, critical_messages: list[str]
) -> None:
    monkeypatch.setattr(
        _FailingDownloadDialog,
        "error",
        requests.exceptions.ConnectionError("Max retries exceeded"),
        raising=False,
    )

    assert download_module.download_module_bundle(None) is None  # type: ignore[arg-type]

    (message,) = critical_messages
    assert "Do you have an internet connection?" in message


def test_expired_login_is_explained_before_logging_in_again(
    monkeypatch: pytest.MonkeyPatch, critical_messages: list[str]
) -> None:
    monkeypatch.setattr(_FailingDownloadDialog, "error", LoginRequiredError(), raising=False)

    download_module.download_module_bundle(None)  # type: ignore[arg-type]

    (login_dialog,) = _CancelledLoginDialog.shown
    (feedback,) = login_dialog.login_widget.feedback
    assert "login has expired" in feedback
