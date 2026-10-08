# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import typing as t
from pathlib import Path
from uuid import UUID, uuid4

import attrs
import pytest

from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.app_model import app_model as app_model_module
from acconeer.exptool.app.new.app_model.file_detective import FileFindings
from acconeer.exptool.app.new.storage import get_module_bundle_path


pytestmark = pytest.mark.usefixtures("qapplication")


class _RecordingBackend:
    def __init__(self) -> None:
        self.tasks: list[t.Any] = []

    def put_task(self, task: t.Any) -> UUID:
        self.tasks.append(task)
        return uuid4()


@attrs.frozen
class _PluginNeedingModuleBundle:
    key: str = "needs_module_bundle"
    title: str = "Needs Module Bundle"
    generation: PluginGeneration = PluginGeneration.A121
    requires_module_bundle_artifact: bool = True

    def create_backend_plugin(self, *_: t.Any) -> t.Any:
        msg = "must not be created in these tests"
        raise AssertionError(msg)


class _AcceptedReplayDialog:
    def __init__(
        self, plugin_options: t.Iterable[t.Any], default_selected: str, **_: t.Any
    ) -> None:
        (self.selected_plugin_option,) = (p for p in plugin_options if p.key == default_selected)

    def exec(self) -> bool:
        return True


def _app_model(backend: _RecordingBackend) -> AppModel:
    return AppModel(backend, [_PluginNeedingModuleBundle()], use_port_updater=False)  # type: ignore[arg-type, list-item]


def _record_errors(app_model: AppModel) -> list[BaseException]:
    errors: list[BaseException] = []
    app_model.sig_error.connect(lambda exception, _traceback: errors.append(exception))
    return errors


def test_plugin_needing_missing_module_bundle_is_refused_with_a_way_forward() -> None:
    backend = _RecordingBackend()
    app_model = _app_model(backend)
    errors = _record_errors(app_model)

    app_model.load_plugin(_PluginNeedingModuleBundle())  # type: ignore[arg-type]

    (error,) = errors
    assert isinstance(error, HandledException)
    assert "Select it in the plugin list" in str(error)
    assert app_model.plugin is None
    assert backend.tasks == []


def test_recording_of_plugin_needing_missing_module_bundle_is_not_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_model_module,
        "investigate_file",
        lambda _path: FileFindings(generation=PluginGeneration.A121, key="needs_module_bundle"),
    )
    monkeypatch.setattr(app_model_module, "SelectPluginToReplayInDialog", _AcceptedReplayDialog)
    backend = _RecordingBackend()
    app_model = _app_model(backend)
    errors = _record_errors(app_model)

    app_model.load_from_file(tmp_path / "recording.h5")

    assert len(errors) == 1
    assert backend.tasks == []


def test_module_bundle_present_at_startup_is_available() -> None:
    get_module_bundle_path().write_bytes(b"module")

    assert _app_model(_RecordingBackend()).module_bundle_available


def test_stored_module_bundle_becomes_available(tmp_path: Path) -> None:
    app_model = _app_model(_RecordingBackend())
    downloaded = tmp_path / "downloaded.bin"
    downloaded.write_bytes(b"module")

    app_model.store_module_bundle(downloaded)

    assert app_model.module_bundle_available
    assert get_module_bundle_path().read_bytes() == b"module"
