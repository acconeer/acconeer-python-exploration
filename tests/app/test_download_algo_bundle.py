# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import importlib
import typing as t
from pathlib import Path

import pytest
import requests

from PySide6.QtWidgets import QDialog, QWidget

from acconeer.exptool._artifact_repository import Artifact, LoginRequiredError
from acconeer.exptool.app.new.storage import get_algo_bundle_path


# The package re-exports a function by the module's name, hiding the module
download_module = importlib.import_module(
    "acconeer.exptool.app.new.ui.components.devsite.download_algo_bundle"
)
pytestmark = pytest.mark.usefixtures("qapplication")


class _PluginRepository:
    def __init__(self, logged_in: bool) -> None:
        self.logged_in = logged_in
        self.downloads: list[Artifact] = []

    def has_logged_in_previously(self) -> bool:
        return self.logged_in

    def download(self, artifact: Artifact, path: str) -> tuple[str, str]:
        self.downloads.append(artifact)
        downloaded_path = Path(path) / "algo_bundle.bin"
        downloaded_path.write_bytes(b"module")
        return str(downloaded_path), "1.0.0"


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


class _LoginIntoGivenRepository:
    def __init__(self, repository: _PluginRepository, *_: t.Any) -> None:
        self.repository = repository

    def exec(self) -> QDialog.DialogCode:
        self.repository.logged_in = True
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
def plugin_repository(monkeypatch: pytest.MonkeyPatch) -> _PluginRepository:
    repository = _PluginRepository(logged_in=False)
    monkeypatch.setattr(download_module, "create_artifact_repository", lambda: repository)
    monkeypatch.setattr(download_module, "LicenseDialog", _AcceptedDialog)
    monkeypatch.setattr(download_module, "LoginDialog", _LoginIntoGivenRepository)
    return repository


@pytest.fixture
def critical_messages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(download_module, "create_artifact_repository", _SavedLogin)
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


def test_algo_bundle_is_downloaded_from_the_plugin_repository(
    plugin_repository: _PluginRepository,
) -> None:
    plugin_repository.logged_in = True

    downloaded_path = download_module.download_algo_bundle(QWidget())

    assert downloaded_path is not None
    assert plugin_repository.downloads == [Artifact.ALGO_BUNDLE]


def test_downloaded_algo_bundle_is_stored_for_later_starts(
    plugin_repository: _PluginRepository,
) -> None:
    plugin_repository.logged_in = True

    stored_path = download_module.download_algo_bundle(QWidget())

    assert stored_path == get_algo_bundle_path()
    assert stored_path.read_bytes() == b"module"


def test_login_happens_in_the_plugin_repository(plugin_repository: _PluginRepository) -> None:
    downloaded_path = download_module.download_algo_bundle(QWidget())

    assert downloaded_path is not None
    assert plugin_repository.downloads == [Artifact.ALGO_BUNDLE]


def test_offline_download_failure_suggests_checking_the_connection(
    monkeypatch: pytest.MonkeyPatch, critical_messages: list[str]
) -> None:
    monkeypatch.setattr(
        _FailingDownloadDialog,
        "error",
        requests.exceptions.ConnectionError("Max retries exceeded"),
        raising=False,
    )

    assert download_module.download_algo_bundle(None) is None  # type: ignore[arg-type]

    (message,) = critical_messages
    assert "Do you have an internet connection?" in message


def test_expired_login_is_explained_before_logging_in_again(
    monkeypatch: pytest.MonkeyPatch, critical_messages: list[str]
) -> None:
    monkeypatch.setattr(_FailingDownloadDialog, "error", LoginRequiredError(), raising=False)

    download_module.download_algo_bundle(None)  # type: ignore[arg-type]

    (login_dialog,) = _CancelledLoginDialog.shown
    (feedback,) = login_dialog.login_widget.feedback
    assert "login has expired" in feedback
