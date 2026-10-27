# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import copy
import json
import typing as t
from pathlib import Path
from unittest.mock import Mock

import attrs
import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import Criticality
from acconeer.exptool.a2.algo._detection_geometry import (
    DETECTION_VOLUME_DATASET_NAME,
    LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME,
    SENSOR_INSTALLATION_DATASET_NAME,
    DetectionVolume,
    SensorInstallation,
)
from acconeer.exptool.a2.algo._plugin_specs.conventional_heatmap import (
    CONVENTIONAL_HEATMAP_PLUGIN,
)
from acconeer.exptool.a2.algo._plugin_specs.motion_detection import MOTION_DETECTION_PLUGIN
from acconeer.exptool.a2.algo._plugin_specs.presence_tracking_wall_mount import (
    PRESENCE_TRACKING_WALL_MOUNT_PLUGIN,
)
from acconeer.exptool.a2.algo._plugin_specs.sparse_iq import SPARSE_IQ_PLUGIN
from acconeer.exptool.a2.algo.noise_normalization.processor import NOISE_NORMALIZATION_GROUP_NAME
from acconeer.exptool.a2.algo.sparse_iq import plugin as sparse_iq
from acconeer.exptool.app.new import PluginPresetBase
from acconeer.exptool.app.new._enums import ConnectionState, PluginGeneration, PluginState
from acconeer.exptool.app.new.app_model import PluginSpec
from acconeer.exptool.app.new.backend import BackendLogger, LogMessage, Message, StatusMessage
from acconeer.exptool.app.new.plugin_loader import load_default_plugins


pytestmark = pytest.mark.usefixtures("qapplication")

A2_PLUGINS = [p for p in load_default_plugins() if p.generation == PluginGeneration.A2]
A2_PLUGIN_PRESETS = [
    pytest.param(
        plugin, preset, id=f"{plugin.key}-{'initial' if preset is None else preset.preset_id.name}"
    )
    for plugin in A2_PLUGINS
    for preset in [None, *(plugin.presets or [])]
]
NOISE_RECORDING_PLUGINS = [p for p in A2_PLUGINS if p is not SPARSE_IQ_PLUGIN]
# The plugins configured by a SensorInstallation and a DetectionVolume.
GEOMETRY_PLUGINS = [
    MOTION_DETECTION_PLUGIN,
    PRESENCE_TRACKING_WALL_MOUNT_PLUGIN,
]
SESSION_CONFIG_CACHING_PLUGINS = [
    SPARSE_IQ_PLUGIN,
    CONVENTIONAL_HEATMAP_PLUGIN,
]


@pytest.fixture(autouse=True)
def backend_log(monkeypatch: pytest.MonkeyPatch) -> list[Message]:
    messages: list[Message] = []
    monkeypatch.setattr(BackendLogger, "_callback", messages.append)
    return messages


def _out_of_range_session_config() -> a2.SessionConfig:
    config = a2.SessionConfig.default()
    config.sensor_config.num_points = 400
    return config


def _lower_receiver_gain(subsweep: t.Any) -> None:
    subsweep.receiver_gain -= 1


def _stretch_range(subsweep: t.Any) -> None:
    subsweep.num_points = 400


def _create_backend_plugin(
    plugin: PluginSpec, messages: t.Optional[list[Message]] = None
) -> t.Any:
    callback = (lambda _: None) if messages is None else messages.append
    return plugin.create_backend_plugin(callback=callback, key=plugin.key)


def _has_errors(state: t.Any) -> bool:
    return any(
        result.criticality == Criticality.ERROR for result in state._collect_validation_results()
    )


def _warnings(backend_log: list[Message]) -> list[str]:
    return [
        message.log_string
        for message in backend_log
        if isinstance(message, LogMessage) and message.log_level == "WARNING"
    ]


def _connected_app_model(backend_plugin_state: object) -> Mock:
    return Mock(
        plugin_state=PluginState.LOADED_IDLE,
        connection_state=ConnectionState.CONNECTED,
        plugin_generation=PluginGeneration.A2,
        backend_plugin_state=backend_plugin_state,
    )


@pytest.mark.parametrize(("plugin", "preset"), A2_PLUGIN_PRESETS)
def test_configuration_is_valid(plugin: PluginSpec, preset: t.Optional[PluginPresetBase]) -> None:
    backend_plugin = plugin.create_backend_plugin(callback=lambda _: None, key=plugin.key)
    if preset is not None:
        backend_plugin.set_preset(preset_id=preset.preset_id.value)

    errors = [
        result
        for result in backend_plugin.shared_state._collect_validation_results()
        if result.criticality == Criticality.ERROR
    ]
    assert errors == []


@pytest.mark.parametrize("plugin", A2_PLUGINS, ids=lambda p: p.key)
def test_initial_state_round_trips_through_the_cache(
    plugin: PluginSpec, caplog: pytest.LogCaptureFixture
) -> None:
    backend_plugin = plugin.create_backend_plugin(callback=lambda _: None, key=plugin.key)
    backend_plugin.teardown()
    reloaded = plugin.create_backend_plugin(callback=lambda _: None, key=plugin.key)
    reloaded.load_from_cache()

    assert "Could not write to cache" not in caplog.text
    assert reloaded.shared_state.session_config == backend_plugin.shared_state.session_config


@pytest.mark.parametrize(
    ("session_config", "startable"),
    [
        (a2.SessionConfig.default(), True),
        (_out_of_range_session_config(), False),
    ],
    ids=["valid", "invalid"],
)
def test_start_requires_a_valid_configuration(
    session_config: a2.SessionConfig, startable: bool
) -> None:
    state = sparse_iq.SharedState(session_config=session_config, metadata=None)
    app_model = _connected_app_model(state)
    view = sparse_iq.ViewPlugin(app_model)

    view.on_backend_state_update(state)
    view.on_app_model_update(app_model)

    assert view.start_button.isEnabled() is startable
    assert view.invalid_config_note.isHidden() is startable


def test_start_requires_valid_input() -> None:
    state = sparse_iq.SharedState(session_config=a2.SessionConfig.default(), metadata=None)
    app_model = _connected_app_model(state)
    view = sparse_iq.ViewPlugin(app_model)
    view.on_backend_state_update(state)

    subsweep_editor = view.session_config_editor._sensor_config_editor._subsweep_config_editors[0]
    subsweep_editor._attrs_config_editor._pidget_mapping["tx_antenna_mask"].sig_update.emit(0)
    view.on_app_model_update(app_model)

    assert not view.start_button.isEnabled()
    assert not view.invalid_config_note.isHidden()


@pytest.mark.parametrize("plugin", SESSION_CONFIG_CACHING_PLUGINS, ids=lambda p: p.key)
@pytest.mark.parametrize(
    ("change", "valid"),
    [(_lower_receiver_gain, True), (_stretch_range, False)],
    ids=["valid", "invalid"],
)
def test_readable_cached_configuration_is_kept(
    plugin: PluginSpec,
    change: t.Callable[[t.Any], None],
    valid: bool,
    backend_log: list[Message],
) -> None:
    backend_plugin = _create_backend_plugin(plugin)
    session_config = copy.deepcopy(backend_plugin.shared_state.session_config)
    change(session_config.sensor_configs[0].subsweeps[0])
    with backend_plugin.h5_cache_file(write=True) as f:
        f.create_dataset("session_config", data=session_config.to_json())

    backend_plugin.load_from_cache()

    assert backend_plugin.shared_state.session_config == session_config
    assert _has_errors(backend_plugin.shared_state) is not valid
    assert _warnings(backend_log) == []


@pytest.mark.parametrize("plugin", A2_PLUGINS, ids=lambda p: p.key)
def test_unreadable_cache_falls_back_to_defaults(
    plugin: PluginSpec, backend_log: list[Message]
) -> None:
    messages: list[Message] = []
    backend_plugin = _create_backend_plugin(plugin, messages)
    default_session_config = copy.deepcopy(backend_plugin.shared_state.session_config)
    with backend_plugin.h5_cache_file(write=True) as f:
        cache_path = Path(f.filename)
    cache_path.write_bytes(b"not an h5 file")

    backend_plugin.load_from_cache()

    assert backend_plugin.shared_state.session_config == default_session_config
    assert len(_warnings(backend_log)) == 1
    assert any(isinstance(message, StatusMessage) for message in messages)

    backend_plugin.teardown()
    _create_backend_plugin(plugin).load_from_cache()

    assert len(_warnings(backend_log)) == 1


def test_partly_read_cache_is_discarded(backend_log: list[Message]) -> None:
    plugin = CONVENTIONAL_HEATMAP_PLUGIN
    backend_plugin = _create_backend_plugin(plugin)
    default_session_config = copy.deepcopy(backend_plugin.shared_state.session_config)
    session_config = copy.deepcopy(default_session_config)
    _lower_receiver_gain(session_config.sensor_configs[0].subsweeps[0])
    with backend_plugin.h5_cache_file(write=True) as f:
        f.create_dataset("session_config", data=session_config.to_json())
        f.create_dataset(backend_plugin.heatmap_config_dataset_name, data="not a heatmap config")

    backend_plugin.load_from_cache()

    assert backend_plugin.shared_state.session_config == default_session_config
    assert len(_warnings(backend_log)) == 1


@pytest.mark.parametrize("plugin", NOISE_RECORDING_PLUGINS, ids=lambda p: p.key)
def test_unloadable_noise_recording_keeps_the_settings(
    plugin: PluginSpec, backend_log: list[Message]
) -> None:
    backend_plugin = _create_backend_plugin(plugin)
    backend_plugin.shared_state.heatmap_plot_orientation.rotation = 90
    with backend_plugin.h5_cache_file(write=True) as f:
        backend_plugin.save_to_cache(f)
        del f["noise_group"]
        noise_group = f.create_group("noise_group").create_group(NOISE_NORMALIZATION_GROUP_NAME)
        noise_group.create_dataset("not_a_recording", data=0)

    reloaded = _create_backend_plugin(plugin)
    reloaded.load_from_cache()

    assert reloaded.shared_state.heatmap_plot_orientation.rotation == 90
    assert reloaded.shared_state.noise_normalization_recording is None
    assert _warnings(backend_log) == ["Could not load noise normalization recording from cache"]


@pytest.mark.parametrize("plugin", GEOMETRY_PLUGINS, ids=lambda p: p.key)
def test_cache_from_before_the_split_is_split(
    plugin: PluginSpec, backend_log: list[Message]
) -> None:
    # A cache written before the split holds one DetectionVolumeConfig.
    legacy = {
        "x_bounds_m": [-3.0, 3.0],
        "y_bounds_m": [0.0, 5.0],
        "z_bounds_m": [-1.5, 1.0],
        "x_rotation": -10.0,
        "y_rotation": 0.0,
        "z_rotation": 0.0,
        "az_angle_range": [-50.0, 50.0],
        "el_angle_range": [-30.0, 30.0],
    }
    backend_plugin = _create_backend_plugin(plugin)
    with backend_plugin.h5_cache_file(write=True) as f:
        backend_plugin.save_to_cache(f)
        del f[SENSOR_INSTALLATION_DATASET_NAME]
        del f[DETECTION_VOLUME_DATASET_NAME]
        f.create_dataset(LEGACY_DETECTION_VOLUME_CONFIG_DATASET_NAME, data=json.dumps(legacy))

    reloaded = _create_backend_plugin(plugin)
    reloaded.load_from_cache()

    # The floor is taken as the bottom of the legacy box.
    assert reloaded.shared_state.sensor_installation == SensorInstallation(
        x_rotation=-10.0, y_rotation=0.0, mount_height_m=1.5
    )
    assert reloaded.shared_state.detection_volume == DetectionVolume(
        x_bounds_m=(-3.0, 3.0),
        y_bounds_m=(0.0, 5.0),
        az_angle_range=(-50.0, 50.0),
    )
    assert _warnings(backend_log) == []


@pytest.mark.parametrize("plugin", GEOMETRY_PLUGINS, ids=lambda p: p.key)
def test_view_shows_the_installation_and_the_volume(plugin: PluginSpec) -> None:
    state = _create_backend_plugin(plugin).shared_state
    app_model = _connected_app_model(state)
    view = plugin.create_view_plugin(app_model)

    view.on_backend_state_update(state)
    view.on_app_model_update(app_model)

    assert view.sensor_installation_editor.get_data() == state.sensor_installation
    assert view.detection_volume_editor.get_data() == state.detection_volume
    assert view.start_button.isEnabled()


@pytest.mark.parametrize("plugin", GEOMETRY_PLUGINS, ids=lambda p: p.key)
def test_partial_box_keeps_start_disabled(plugin: PluginSpec) -> None:
    state = _create_backend_plugin(plugin).shared_state
    state.detection_volume = DetectionVolume(x_bounds_m=(-3.0, 3.0), end_m=5.0)
    app_model = _connected_app_model(state)
    view = plugin.create_view_plugin(app_model)

    view.on_backend_state_update(state)
    view.on_app_model_update(app_model)

    assert not view.start_button.isEnabled()
    assert not view.invalid_config_note.isHidden()


@pytest.mark.parametrize("plugin", GEOMETRY_PLUGINS, ids=lambda p: p.key)
def test_the_preset_box_height_follows_the_mount_height(plugin: PluginSpec) -> None:
    backend_plugin = _create_backend_plugin(plugin)
    state = backend_plugin.shared_state
    preset_session_config = state.session_config
    lowered = attrs.evolve(state.sensor_installation, mount_height_m=1.0)

    backend_plugin.update_sensor_installation(sensor_installation=lowered)

    # The box keeps the room's height, from the new floor up, and the
    # sensor configuration covers it.
    assert state.session_config != preset_session_config
