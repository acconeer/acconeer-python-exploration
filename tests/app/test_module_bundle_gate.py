# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import typing as t
from pathlib import Path
from uuid import UUID, uuid4

import attrs
import pytest

from acconeer.exptool._artifact_repository import install_module_bundle
from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app import _ExptoolArgumentParser, install_startup_module_bundle
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.app_model import app_model as app_model_module
from acconeer.exptool.app.new.app_model.file_detective import FileFindings
from acconeer.exptool.app.new.backend import BackendLogger
from acconeer.exptool.app.new.backend import _model as model_module
from acconeer.exptool.app.new.storage import get_module_bundle_extract_dir, get_module_bundle_path


pytestmark = pytest.mark.usefixtures("qapplication")


@pytest.fixture(autouse=True)
def installs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path]]:
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        app_model_module,
        "install_module_bundle",
        lambda zip_path, extract_dir: calls.append((zip_path, extract_dir)),
    )
    return calls


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


def _try_install(app_model: AppModel) -> None:
    app_model.try_install_module_bundle(get_module_bundle_path(), get_module_bundle_extract_dir())


def test_installed_module_bundle_is_available() -> None:
    get_module_bundle_path().write_bytes(b"module")
    app_model = _app_model(_RecordingBackend())

    _try_install(app_model)

    assert app_model.module_bundle_available


def _import_task() -> tuple[str, dict[str, t.Any]]:
    return ("import_module_bundle", {"extract_dir": get_module_bundle_extract_dir()})


def test_module_bundle_is_installed(installs: list[tuple[Path, Path]]) -> None:
    get_module_bundle_path().write_bytes(b"module")

    _try_install(_app_model(_RecordingBackend()))

    assert installs == [(get_module_bundle_path(), get_module_bundle_extract_dir())]


def test_installed_module_bundle_is_imported_by_the_backend() -> None:
    get_module_bundle_path().write_bytes(b"module")
    backend = _RecordingBackend()

    _try_install(_app_model(backend))

    assert backend.tasks == [_import_task()]


def test_module_bundle_refused_by_the_install_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refuse(*_: t.Any) -> None:
        msg = "/somewhere/_node.py would shadow '_node' from the bundle."
        raise ValueError(msg)

    monkeypatch.setattr(app_model_module, "install_module_bundle", _refuse)
    get_module_bundle_path().write_bytes(b"module")
    app_model = _app_model(_RecordingBackend())
    errors = _record_errors(app_model)

    _try_install(app_model)

    (error,) = errors
    assert "would shadow" in str(error)
    assert not app_model.module_bundle_available


def test_backend_imports_the_extracted_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    imported: list[Path] = []
    monkeypatch.setattr(model_module, "import_module_bundle", imported.append)
    monkeypatch.setattr(BackendLogger, "_callback", lambda _: None)

    model_module.Model(task_callback=lambda _: None).import_module_bundle(extract_dir=tmp_path)

    assert imported == [tmp_path]


def test_failed_install_is_reported_right_away(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_model_module, "install_module_bundle", install_module_bundle)
    get_module_bundle_path().write_bytes(b"not a zip")
    app_model = _app_model(_RecordingBackend())
    errors = _record_errors(app_model)

    _try_install(app_model)

    (error,) = errors
    assert "Could not install the module bundle" in str(error)
    assert not app_model.module_bundle_available


def test_module_bundle_present_at_startup_is_left_for_the_caller_to_install(
    installs: list[tuple[Path, Path]],
) -> None:
    get_module_bundle_path().write_bytes(b"module")
    backend = _RecordingBackend()

    app_model = _app_model(backend)

    assert installs == []
    assert backend.tasks == []
    assert not app_model.module_bundle_available


def _install_at_startup(app_model: AppModel, *options: str) -> None:
    install_startup_module_bundle(_ExptoolArgumentParser().parse_args(options), app_model)


def test_module_bundle_option_installs_that_zip_apart_from_the_downloaded_one(
    tmp_path: Path, installs: list[tuple[Path, Path]]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")
    get_module_bundle_path().write_bytes(b"downloaded")

    _install_at_startup(_app_model(_RecordingBackend()), "--module-bundle", str(zip_path))

    ((installed, extract_dir),) = installs
    assert installed == zip_path
    assert extract_dir != get_module_bundle_extract_dir()


def test_downloaded_module_bundle_is_installed_at_startup(
    installs: list[tuple[Path, Path]],
) -> None:
    get_module_bundle_path().write_bytes(b"downloaded")

    _install_at_startup(_app_model(_RecordingBackend()))

    assert installs == [(get_module_bundle_path(), get_module_bundle_extract_dir())]


def test_module_bundle_option_refuses_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        _ExptoolArgumentParser().parse_args(["--module-bundle", str(tmp_path / "missing.zip")])

    assert f"No module bundle at '{tmp_path / 'missing.zip'}'" in capsys.readouterr().err
