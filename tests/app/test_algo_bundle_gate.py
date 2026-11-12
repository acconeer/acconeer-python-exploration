# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import argparse
import hashlib
import logging
import typing as t
from collections.abc import Collection
from pathlib import Path
from uuid import UUID, uuid4

import attrs
import pytest

from acconeer.exptool._artifact_repository import ACCEPTED_DIGESTS, install_algo_bundle
from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app import (
    _ExptoolArgumentParser,
    _parse_args,
    create_app_model,
    install_startup_algo_bundle,
)
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.app_model import app_model as app_model_module
from acconeer.exptool.app.new.app_model.file_detective import FileFindings
from acconeer.exptool.app.new.backend import BackendLogger
from acconeer.exptool.app.new.backend import _model as model_module
from acconeer.exptool.app.new.storage import get_algo_bundle_extract_dir, get_algo_bundle_path


pytestmark = pytest.mark.usefixtures("qapplication")


@pytest.fixture
def checked_digests() -> list[Collection[str] | None]:
    """The digests each install accepted, None where it skipped the check"""
    return []


@pytest.fixture(autouse=True)
def installs(
    monkeypatch: pytest.MonkeyPatch, checked_digests: list[Collection[str] | None]
) -> list[tuple[Path, Path]]:
    calls: list[tuple[Path, Path]] = []

    def _install(
        zip_path: Path, extract_dir: Path, *, accepted_digests: Collection[str] | None
    ) -> None:
        calls.append((zip_path, extract_dir))
        checked_digests.append(accepted_digests)

    monkeypatch.setattr(app_model_module, "install_algo_bundle", _install)
    return calls


class _RecordingBackend:
    def __init__(self) -> None:
        self.tasks: list[t.Any] = []

    def put_task(self, task: t.Any) -> UUID:
        self.tasks.append(task)
        return uuid4()


@attrs.frozen
class _PluginNeedingAlgoBundle:
    key: str = "needs_algo_bundle"
    title: str = "Needs Algo Bundle"
    generation: PluginGeneration = PluginGeneration.A121
    requires_algo_bundle_artifact: bool = True

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
    return AppModel(
        backend,  # type: ignore[arg-type]
        [_PluginNeedingAlgoBundle()],  # type: ignore[list-item]
        use_port_updater=False,
        algo_bundle=get_algo_bundle_path(),
    )


def _record_errors(app_model: AppModel) -> list[BaseException]:
    errors: list[BaseException] = []
    app_model.sig_error.connect(lambda exception, _traceback: errors.append(exception))
    return errors


def test_plugin_needing_missing_algo_bundle_is_refused_with_a_way_forward() -> None:
    backend = _RecordingBackend()
    app_model = _app_model(backend)
    errors = _record_errors(app_model)

    app_model.load_plugin(_PluginNeedingAlgoBundle())  # type: ignore[arg-type]

    (error,) = errors
    assert isinstance(error, HandledException)
    assert "Select it in the plugin list" in str(error)
    assert app_model.plugin is None
    assert backend.tasks == []


def test_recording_of_plugin_needing_missing_algo_bundle_is_not_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_model_module,
        "investigate_file",
        lambda _path: FileFindings(
            generation=PluginGeneration.A121, key="needs_algo_bundle", et_version=None
        ),
    )
    monkeypatch.setattr(app_model_module, "SelectPluginToReplayInDialog", _AcceptedReplayDialog)
    backend = _RecordingBackend()
    app_model = _app_model(backend)
    errors = _record_errors(app_model)

    app_model.load_from_file(tmp_path / "recording.h5")

    assert len(errors) == 1
    assert backend.tasks == []


def test_installed_algo_bundle_is_available() -> None:
    get_algo_bundle_path().write_bytes(b"module")
    app_model = _app_model(_RecordingBackend())

    app_model.try_install_algo_bundle()

    assert app_model.algo_bundle_available


def _import_task() -> tuple[str, dict[str, t.Any]]:
    return ("import_algo_bundle", {"extract_dir": get_algo_bundle_extract_dir()})


def test_algo_bundle_is_installed(installs: list[tuple[Path, Path]]) -> None:
    get_algo_bundle_path().write_bytes(b"module")

    _app_model(_RecordingBackend()).try_install_algo_bundle()

    assert installs == [(get_algo_bundle_path(), get_algo_bundle_extract_dir())]


def test_installed_algo_bundle_is_imported_by_the_backend() -> None:
    get_algo_bundle_path().write_bytes(b"module")
    backend = _RecordingBackend()

    _app_model(backend).try_install_algo_bundle()

    assert backend.tasks == [_import_task()]


def test_algo_bundle_refused_by_the_install_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refuse(*_: t.Any, **__: t.Any) -> None:
        msg = "/somewhere/_node.py would shadow '_node' from the bundle."
        raise ValueError(msg)

    monkeypatch.setattr(app_model_module, "install_algo_bundle", _refuse)
    get_algo_bundle_path().write_bytes(b"module")
    app_model = _app_model(_RecordingBackend())
    errors = _record_errors(app_model)

    app_model.try_install_algo_bundle()

    (error,) = errors
    assert "would shadow" in str(error)
    assert not app_model.algo_bundle_available


def test_backend_imports_the_extracted_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    imported: list[Path] = []
    monkeypatch.setattr(model_module, "import_algo_bundle", imported.append)
    monkeypatch.setattr(BackendLogger, "_callback", lambda _: None)

    model_module.Model(task_callback=lambda _: None).import_algo_bundle(extract_dir=tmp_path)

    assert imported == [tmp_path]


def test_failed_install_is_reported_right_away(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_model_module, "install_algo_bundle", install_algo_bundle)
    get_algo_bundle_path().write_bytes(b"not a zip")
    app_model = _app_model(_RecordingBackend())
    errors = _record_errors(app_model)

    app_model.try_install_algo_bundle()

    (error,) = errors
    assert "Could not install the algo bundle" in str(error)
    assert not app_model.algo_bundle_available


def test_algo_bundle_present_at_startup_is_left_for_the_caller_to_install(
    installs: list[tuple[Path, Path]],
) -> None:
    get_algo_bundle_path().write_bytes(b"module")
    backend = _RecordingBackend()

    app_model = _app_model(backend)

    assert installs == []
    assert backend.tasks == []
    assert not app_model.algo_bundle_available


def _launch(*options: str) -> tuple[argparse.Namespace, AppModel]:
    args = _parse_args(_ExptoolArgumentParser(), ["--no-port-updater", *options])
    plugins = [_PluginNeedingAlgoBundle()]
    return args, create_app_model(args, plugins, _RecordingBackend())  # type: ignore[arg-type]


def _install_at_startup(*options: str) -> None:
    install_startup_algo_bundle(*_launch(*options))


def test_algo_bundle_option_installs_that_zip_instead_of_the_downloaded_one(
    tmp_path: Path, installs: list[tuple[Path, Path]]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")
    get_algo_bundle_path().write_bytes(b"downloaded")

    _install_at_startup("--algo-bundle", str(zip_path))

    assert [installed for installed, _ in installs] == [zip_path]
    assert get_algo_bundle_path().read_bytes() == b"downloaded"


def test_downloaded_algo_bundle_is_installed_at_startup(
    installs: list[tuple[Path, Path]],
) -> None:
    get_algo_bundle_path().write_bytes(b"downloaded")

    _install_at_startup()

    assert installs == [(get_algo_bundle_path(), get_algo_bundle_extract_dir())]


def test_algo_bundle_option_refuses_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        _ExptoolArgumentParser().parse_args(["--algo-bundle", str(tmp_path / "missing.zip")])

    assert f"No algo bundle at '{tmp_path / 'missing.zip'}'" in capsys.readouterr().err


def test_algo_bundle_variable_installs_that_zip_instead_of_the_downloaded_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installs: list[tuple[Path, Path]]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")
    get_algo_bundle_path().write_bytes(b"downloaded")
    monkeypatch.setenv("ET_ALGO_BUNDLE", str(zip_path))

    _install_at_startup()

    assert [installed for installed, _ in installs] == [zip_path]


def test_algo_bundle_option_takes_precedence_over_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installs: list[tuple[Path, Path]]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")
    monkeypatch.setenv("ET_ALGO_BUNDLE", str(tmp_path / "missing.zip"))

    _install_at_startup("--algo-bundle", str(zip_path))

    assert [installed for installed, _ in installs] == [zip_path]


def test_algo_bundle_variable_refuses_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ET_ALGO_BUNDLE", str(tmp_path / "missing.zip"))

    with pytest.raises(SystemExit):
        _parse_args(_ExptoolArgumentParser(), [])

    err = capsys.readouterr().err
    assert f"No algo bundle at '{tmp_path / 'missing.zip'}'" in err
    assert "ET_ALGO_BUNDLE" in err
    assert "--algo-bundle" not in err


def test_algo_bundle_option_blames_itself_for_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")
    monkeypatch.setenv("ET_ALGO_BUNDLE", str(zip_path))

    with pytest.raises(SystemExit):
        _parse_args(_ExptoolArgumentParser(), ["--algo-bundle", str(tmp_path / "missing.zip")])

    err = capsys.readouterr().err
    assert "--algo-bundle" in err
    assert "ET_ALGO_BUNDLE" not in err


def test_algo_bundle_option_is_checked_by_default(
    tmp_path: Path, checked_digests: list[Collection[str] | None]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")

    _install_at_startup("--algo-bundle", str(zip_path))

    assert checked_digests == [ACCEPTED_DIGESTS]


def test_skip_option_skips_the_check_of_the_algo_bundle_option(
    tmp_path: Path, checked_digests: list[Collection[str] | None]
) -> None:
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"module")

    _install_at_startup(
        "--algo-bundle",
        str(zip_path),
        "--dangerously-skip-integrity-check",
    )

    assert checked_digests == [None]


def test_skip_option_skips_the_check_of_the_downloaded_bundle(
    checked_digests: list[Collection[str] | None],
) -> None:
    get_algo_bundle_path().write_bytes(b"downloaded")

    _install_at_startup("--dangerously-skip-integrity-check")

    assert checked_digests == [None]


def test_skip_option_skips_the_check_of_a_bundle_downloaded_after_start(
    checked_digests: list[Collection[str] | None],
) -> None:
    args, app_model = _launch("--dangerously-skip-integrity-check")
    install_startup_algo_bundle(args, app_model)
    get_algo_bundle_path().write_bytes(b"downloaded")

    app_model.try_install_algo_bundle()

    assert checked_digests == [None]


def test_skip_option_warns(caplog: pytest.LogCaptureFixture) -> None:
    get_algo_bundle_path().write_bytes(b"downloaded")

    with caplog.at_level(logging.WARNING):
        _install_at_startup("--dangerously-skip-integrity-check")

    assert "integrity" in caplog.text


def test_skip_option_logs_the_digest_of_the_unchecked_bundle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    get_algo_bundle_path().write_bytes(b"downloaded")

    with caplog.at_level(logging.WARNING):
        _install_at_startup("--dangerously-skip-integrity-check")

    assert hashlib.sha256(b"downloaded").hexdigest()[:12] in caplog.text


def test_skip_option_is_hidden_from_help() -> None:
    assert "--dangerously-skip-integrity-check" not in _ExptoolArgumentParser().format_help()


def test_failed_check_of_algo_bundle_option_suggests_the_skip_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_model_module, "install_algo_bundle", install_algo_bundle)
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(b"a bundle of my own")
    args, app_model = _launch("--algo-bundle", str(zip_path))
    errors = _record_errors(app_model)

    install_startup_algo_bundle(args, app_model)

    (error,) = errors
    assert "--dangerously-skip-integrity-check" in str(error)


def test_failed_check_of_downloaded_bundle_keeps_the_skip_option_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_model_module, "install_algo_bundle", install_algo_bundle)
    get_algo_bundle_path().write_bytes(b"corrupt")
    args, app_model = _launch()
    errors = _record_errors(app_model)

    install_startup_algo_bundle(args, app_model)

    (error,) = errors
    assert "--dangerously-skip-integrity-check" not in str(error)


def _store_and_install(app_model: AppModel) -> None:
    get_algo_bundle_path().write_bytes(b"module")
    get_algo_bundle_extract_dir().mkdir()
    app_model.try_install_algo_bundle()


def test_deleting_the_algo_bundle_removes_its_files() -> None:
    app_model = _app_model(_RecordingBackend())
    _store_and_install(app_model)

    app_model.delete_algo_bundle()

    assert not get_algo_bundle_path().exists()
    assert not get_algo_bundle_extract_dir().exists()


def test_deleting_the_algo_bundle_unloads_the_plugin_that_needs_it() -> None:
    app_model = _app_model(_RecordingBackend())
    _store_and_install(app_model)
    app_model.load_plugin(_PluginNeedingAlgoBundle())  # type: ignore[arg-type]

    app_model.delete_algo_bundle()

    assert app_model.plugin is None
    assert not app_model.algo_bundle_available


def test_deleting_an_installed_algo_bundle_needs_a_restart_before_the_next() -> None:
    app_model = _app_model(_RecordingBackend())
    _store_and_install(app_model)

    app_model.delete_algo_bundle()

    assert app_model.algo_bundle_restart_needed


def test_deleting_a_algo_bundle_that_failed_to_install_needs_no_restart() -> None:
    get_algo_bundle_path().write_bytes(b"corrupt")
    app_model = _app_model(_RecordingBackend())

    app_model.delete_algo_bundle()

    assert not app_model.algo_bundle_restart_needed


def test_failed_install_points_to_the_delete_badge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_model_module, "install_algo_bundle", install_algo_bundle)
    get_algo_bundle_path().write_bytes(b"corrupt")
    app_model = _app_model(_RecordingBackend())
    errors = _record_errors(app_model)

    app_model.try_install_algo_bundle()

    (error,) = errors
    assert '"delete"' in str(error)


def _unexpected_bundle_error(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(app_model_module, "install_algo_bundle", install_algo_bundle)
    get_algo_bundle_path().write_bytes(b"corrupt")
    app_model = _app_model(_RecordingBackend())
    errors = _record_errors(app_model)

    app_model.try_install_algo_bundle()

    (error,) = errors
    return str(error)


def test_unexpected_bundle_error_opens_with_what_went_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _unexpected_bundle_error(monkeypatch)

    assert error.split("\n\n")[0] == (
        "Could not install the algo bundle, since this ET release expects a different one."
    )


def test_unexpected_bundle_error_gives_the_digest_a_line_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _unexpected_bundle_error(monkeypatch)

    assert hashlib.sha256(b"corrupt").hexdigest() in error.splitlines()


def test_unexpected_bundle_error_suggests_deleting_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _unexpected_bundle_error(monkeypatch)

    assert error.count("delete") == 1
