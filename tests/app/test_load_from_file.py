# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t
from pathlib import Path
from uuid import UUID, uuid4

import h5py
import pytest

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
