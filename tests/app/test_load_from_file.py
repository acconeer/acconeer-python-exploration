# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t
from importlib.resources import files
from pathlib import Path
from uuid import UUID, uuid4

import h5py
import pytest
from tests.processing.a121.data_files import expected_output, recorded_data

from acconeer.exptool import a111
from acconeer.exptool.a111._clients.mock.client import MockClient
from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.app_model import app_model as app_model_module
from acconeer.exptool.app.new.plugin_loader import load_default_plugins


pytestmark = pytest.mark.usefixtures("qapplication")


class _NullBackend:
    def put_task(self, task: t.Any) -> UUID:
        return uuid4()


class _AbortedReplaySelection:
    """Stands in for the replay dialog, recording what it would offer"""

    offered: t.ClassVar[list[dict[str, t.Any]]] = []

    def __init__(self, **kwargs: t.Any) -> None:
        self.offered.append(kwargs)

    def exec(self) -> bool:
        return False


@pytest.fixture
def app_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppModel:
    _AbortedReplaySelection.offered = []
    monkeypatch.setattr(app_model_module, "SelectPluginToReplayInDialog", _AbortedReplaySelection)
    return AppModel(
        _NullBackend(),  # type: ignore[arg-type]
        load_default_plugins(),
        use_port_updater=False,
        algo_bundle=tmp_path / "algo_bundle.zip",
    )


def _recording(path: Path, generation: PluginGeneration) -> Path:
    """A recording without an algo key, as the example scripts make"""
    with h5py.File(path, "w") as f:
        f.create_dataset("generation", data=generation.value.encode())
        f.create_dataset("lib_version", data=b"7.18.0")
    return path


@pytest.mark.parametrize(
    ("loaded", "recorded"),
    [
        ((PluginGeneration.A121, "distance_detector"), PluginGeneration.A2),
        ((PluginGeneration.A2, "capon_heatmap"), PluginGeneration.A121),
    ],
)
def test_a_recording_of_the_other_generation_offers_its_own_plugins(
    app_model: AppModel,
    tmp_path: Path,
    loaded: tuple[PluginGeneration, str],
    recorded: PluginGeneration,
) -> None:
    (generation, key) = loaded
    app_model.set_plugin_generation(generation)
    app_model.load_plugin(app_model.find_plugin(key, generation))

    app_model.load_from_file(_recording(tmp_path / "recording.h5", recorded))

    (offered,) = _AbortedReplaySelection.offered
    assert offered["current_plugin_key"] is None
    assert offered["default_selected"] in [p.key for p in offered["plugin_options"]]


def _a111_recording(directory: Path) -> Path:
    client = MockClient()
    config = a111.EnvelopeServiceConfig()
    recorder = a111.recording.Recorder(
        sensor_config=config, session_info=client.start_session(config)
    )
    recorder.sample(*client.get_next())
    recorder.close()
    path = directory / "recording.h5"
    a111.recording.save(path, recorder.record)
    return path


def _processing_output(directory: Path) -> Path:
    path = directory / "recording.h5"
    path.write_bytes((files(expected_output) / "presence-default.h5").read_bytes())
    return path


def _truncated_recording(directory: Path) -> Path:
    recording = (files(recorded_data) / "presence-default.h5").read_bytes()
    path = directory / "recording.h5"
    path.write_bytes(recording[: len(recording) // 2])
    return path


def _config(directory: Path) -> Path:
    path = directory / "config.json"
    path.write_text("{}")
    return path


@pytest.mark.parametrize(
    ("make_file", "reason"),
    [
        (_a111_recording, "python -m acconeer.exptool.app and pick A111"),
        (_processing_output, "not an Exploration Tool recording"),
        (_truncated_recording, "Cannot read recording.h5"),
        (_config, "only .h5"),
    ],
)
def test_refused_file_tells_why(
    app_model: AppModel, tmp_path: Path, make_file: t.Callable[[Path], Path], reason: str
) -> None:
    errors: list[BaseException] = []
    app_model.sig_error.connect(lambda exception, _traceback: errors.append(exception))

    app_model.load_from_file(make_file(tmp_path))

    (error,) = errors
    assert reason in str(error)
