# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.backend import BackendPluginStateMessage
from acconeer.exptool.app.new.plugin_loader import load_default_plugins


pytestmark = pytest.mark.usefixtures("qapplication")


class _NullBackend:
    def put_task(self, task: t.Any) -> UUID:
        return uuid4()


@pytest.fixture
def app_model(tmp_path: Path) -> AppModel:
    app_model = AppModel(
        _NullBackend(),  # type: ignore[arg-type]
        load_default_plugins(),
        use_port_updater=False,
        plugin_generation=PluginGeneration.A2,
        algo_bundle=tmp_path / "algo_bundle.zip",
    )
    app_model.load_plugin(app_model.find_plugin("conventional_heatmap", PluginGeneration.A2))
    return app_model


def test_the_state_of_the_loaded_plugin_is_shown(app_model: AppModel) -> None:
    state = object()

    app_model._handle_backend_message(
        BackendPluginStateMessage(
            state=state, plugin_key="conventional_heatmap", plugin_generation=PluginGeneration.A2
        )
    )

    assert app_model.backend_plugin_state is state


@pytest.mark.parametrize(
    ("key", "generation"),
    [("sparse_iq", PluginGeneration.A2), ("conventional_heatmap", PluginGeneration.A121)],
)
def test_the_state_of_a_plugin_switched_away_from_is_dropped(
    app_model: AppModel, key: str, generation: PluginGeneration
) -> None:
    """It was sent before the switch, but arrives after it"""
    app_model._handle_backend_message(
        BackendPluginStateMessage(state=object(), plugin_key=key, plugin_generation=generation)
    )

    assert app_model.backend_plugin_state is None
