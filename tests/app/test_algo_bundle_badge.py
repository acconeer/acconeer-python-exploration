# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import hashlib
import os
import typing as t
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from PySide6.QtWidgets import QPushButton, QWidget

from acconeer.exptool.app.new import PluginFamily, PluginGeneration, PluginPresetBase
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.pluginbase import BundledPluginSpec
from acconeer.exptool.app.new.storage import get_algo_bundle_path
from acconeer.exptool.app.new.ui.stream_tab import plugin_widget
from acconeer.exptool.app.new.ui.stream_tab.plugin_widget import PluginSelection


pytestmark = pytest.mark.usefixtures("qapplication")


class _PresetId(Enum):
    DEFAULT = auto()


_PLUGIN_NEEDING_ALGO_BUNDLE = BundledPluginSpec(
    generation=PluginGeneration.A121,
    key="needs_algo_bundle",
    title="Needs Algo Bundle",
    family=PluginFamily.REF_APP,
    presets=[PluginPresetBase(name="Default", preset_id=_PresetId.DEFAULT)],
    default_preset_id=_PresetId.DEFAULT,
)


class _RecordingBackend:
    def __init__(self) -> None:
        self.tasks: list[t.Any] = []

    def put_task(self, task: t.Any) -> UUID:
        self.tasks.append(task)
        return uuid4()


@pytest.fixture
def app_model() -> AppModel:
    return AppModel(
        _RecordingBackend(),  # type: ignore[arg-type]
        [_PLUGIN_NEEDING_ALGO_BUNDLE],
        use_port_updater=False,
        algo_bundle=get_algo_bundle_path(),
    )


@pytest.fixture
def selection(app_model: AppModel) -> t.Iterator[PluginSelection]:
    parent = QWidget()
    yield PluginSelection(app_model, [_PLUGIN_NEEDING_ALGO_BUNDLE], parent)
    parent.deleteLater()


def _badge(app_model: AppModel, selection: PluginSelection) -> QPushButton:
    app_model.broadcast()
    badge = selection.findChild(QPushButton, "algo_bundle_badge")
    assert badge is not None
    return badge


def test_badge_without_a_stored_bundle_says_download(
    app_model: AppModel, selection: PluginSelection
) -> None:
    badge = _badge(app_model, selection)

    assert badge.text() == "download"
    assert not badge.isEnabled()


def test_badge_of_an_installed_bundle_says_installed(
    app_model: AppModel, selection: PluginSelection
) -> None:
    get_algo_bundle_path().write_bytes(b"module")
    app_model.algo_bundle_available = True

    badge = _badge(app_model, selection)

    assert badge.text() == "installed"
    assert badge.isEnabled()


def test_badge_of_a_stored_bundle_that_failed_to_install_says_delete(
    app_model: AppModel, selection: PluginSelection
) -> None:
    get_algo_bundle_path().write_bytes(b"corrupt")

    badge = _badge(app_model, selection)

    assert badge.text() == "delete"
    assert badge.isEnabled()


def test_badge_of_a_developer_bundle_tells_where_it_is(
    app_model: AppModel, selection: PluginSelection, tmp_path: Path
) -> None:
    app_model.algo_bundle = _write_bundle(tmp_path / "bundle.zip")

    badge = _badge(app_model, selection)

    assert badge.text() == "developer"
    assert not badge.isEnabled()
    assert str(tmp_path / "bundle.zip") in badge.toolTip()
    assert "failed" in badge.toolTip()


_NOON_UTC = datetime(2026, 10, 22, 12, tzinfo=timezone.utc).timestamp()


def _write_bundle(path: Path, content: bytes = b"module") -> Path:
    path.write_bytes(content)
    os.utime(path, (_NOON_UTC, _NOON_UTC))
    return path


def test_badge_of_an_installed_bundle_tells_when_it_was_downloaded(
    app_model: AppModel, selection: PluginSelection
) -> None:
    _write_bundle(get_algo_bundle_path())
    app_model.algo_bundle_available = True

    badge = _badge(app_model, selection)

    assert "2026-10-22" in badge.toolTip()


def test_badge_of_a_bundle_that_failed_to_install_tells_when_it_was_downloaded(
    app_model: AppModel, selection: PluginSelection
) -> None:
    _write_bundle(get_algo_bundle_path())

    badge = _badge(app_model, selection)

    assert "2026-10-22" in badge.toolTip()


def test_badge_of_a_developer_bundle_tells_when_it_was_built(
    app_model: AppModel, selection: PluginSelection, tmp_path: Path
) -> None:
    app_model.algo_bundle = _write_bundle(tmp_path / "bundle.zip")

    badge = _badge(app_model, selection)

    assert "2026-10-22" in badge.toolTip()


def test_badge_of_a_developer_bundle_tells_its_digest(
    app_model: AppModel, selection: PluginSelection, tmp_path: Path
) -> None:
    app_model.algo_bundle = _write_bundle(tmp_path / "bundle.zip")

    badge = _badge(app_model, selection)

    assert hashlib.sha256(b"module").hexdigest()[:12] in badge.toolTip()


@pytest.mark.parametrize("confirmed", [True, False])
def test_clicking_the_badge_deletes_the_bundle_once_confirmed(
    app_model: AppModel,
    selection: PluginSelection,
    monkeypatch: pytest.MonkeyPatch,
    confirmed: bool,
) -> None:
    monkeypatch.setattr(plugin_widget, "_confirm_algo_bundle_deletion", lambda *_, **__: confirmed)
    get_algo_bundle_path().write_bytes(b"corrupt")
    badge = _badge(app_model, selection)

    badge.click()

    assert get_algo_bundle_path().exists() != confirmed
    assert badge.text() == ("download" if confirmed else "delete")


def test_plugin_is_not_downloaded_again_before_a_restart(
    app_model: AppModel, selection: PluginSelection, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads: list[t.Any] = []
    monkeypatch.setattr(plugin_widget, "download_algo_bundle", downloads.append)
    errors: list[BaseException] = []
    app_model.sig_error.connect(lambda exception, _traceback: errors.append(exception))
    app_model.algo_bundle_restart_needed = True

    (button,) = selection.button_group.buttons()
    button.click()

    assert downloads == []
    (error,) = errors
    assert "Restart ET before you download the algo bundle again" in str(error)
