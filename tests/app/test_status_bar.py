# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication

from acconeer.exptool.app.new.ui import status_bar


@pytest.fixture(autouse=True, scope="module")
def qapplication() -> QApplication:
    return QApplication.instance() or QApplication()


def test_version_check_thread_is_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(status_bar, "check_package_outdated", lambda name, version: (False, None))
    monkeypatch.setattr(status_bar, "get_latest_changelog", lambda: "")

    button = status_bar.VersionButton(app_model=None, parent=None)  # type: ignore[arg-type]

    # A non-daemon thread would block interpreter exit for as long as the
    # version check stalls.
    assert button._version_thread.daemon

    button._version_thread.join(timeout=5)
