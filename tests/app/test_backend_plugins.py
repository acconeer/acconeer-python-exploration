# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
from __future__ import annotations

import typing as t
from pathlib import Path

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.bilateration._plugin import BILATERATION_PLUGIN
from acconeer.exptool.a121.algo.speed._detector_plugin import SPEED_DETECTOR_PLUGIN
from acconeer.exptool.app.new import PluginGeneration, PluginState
from acconeer.exptool.app.new.app_model import PluginSpec
from acconeer.exptool.app.new.backend import (
    Backend,
    GeneralMessage,
    MpBackend,
    PlotMessage,
    PluginStateMessage,
    Task,
)
from acconeer.exptool.app.new.backend._backend import FromBackendQueueItem
from acconeer.exptool.app.new.plugin_loader import load_default_plugins


# number of calls the plugin should request from each application
NUM_CALLS_TO_REQUEST = 2

# pytest-magic for a module-wide timeout of 60s
pytestmark = pytest.mark.timeout(60)


class CaptureSaveableFile:
    """
    A small wrapper that captures the "saveable_file" message and stores the path
    to a member variable.
    """

    _backend: Backend
    saveable_file_path: t.Optional[Path]

    def __init__(self, backend: Backend) -> None:
        self._backend = backend
        self.saveable_file_path = None

    @classmethod
    def wrap(cls, backend: Backend) -> Backend:
        return t.cast(Backend, cls(backend))

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._backend, name)

    def recv(self, timeout: t.Optional[float] = None) -> FromBackendQueueItem:
        received = self._backend.recv(timeout=timeout)

        if isinstance(received, GeneralMessage) and received.name == "saveable_file":
            self.saveable_file_path = received.data
            received = self._backend.recv(timeout=timeout)

        return received


def _plugin_id(p: PluginSpec) -> str:
    return p.key


class TestBackendPlugins:
    """Tests that define the common behaviour of BackendPlugins"""

    @pytest.fixture(params=load_default_plugins(), ids=_plugin_id)
    def plugin(self, request: pytest.FixtureRequest) -> PluginSpec:
        plugin = t.cast(PluginSpec, request.param)

        if plugin.generation not in [PluginGeneration.A121]:
            pytest.xfail(
                "These tests uses a mock client. Only A121 has a mock client at the moment."
            )
        else:
            return plugin

    @pytest.fixture
    def extra_tasks(self, plugin: PluginSpec) -> t.Iterable[Task]:
        if plugin is BILATERATION_PLUGIN:
            return [
                ("update_sensor_ids", dict(sensor_ids=[1, 2])),
            ]
        else:
            return []

    @pytest.fixture
    def backend(
        self,
        tasks: t.Any,
        assert_messages: t.Callable[..., None],
        plugin: PluginSpec,
        extra_tasks: t.Iterable[Task],
    ) -> t.Iterator[Backend]:
        b = CaptureSaveableFile.wrap(MpBackend())
        b.start()
        b.put_task(tasks.CONNECT_CLIENT_TASK[plugin.generation])
        assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])

        b.put_task(tasks.load_plugin_task(plugin))
        assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])

        for extra_task in extra_tasks:
            b.put_task(extra_task)
            assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])

        yield b
        b.stop()

    def test_session_lifecycle(
        self,
        backend: Backend,
        plugin: PluginSpec,
        assert_messages: t.Callable[..., None],
        assert_num_calls: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        # Some backend plugins need to calibrate before starting session
        backend.put_task(tasks.CALIBRATE_DETECTOR_TASK)
        assert_messages(
            backend,
            received=[tasks.ANY_CLOSED_TASK],
            # If the backend plugin does not have a "calibrate_detector",
            # ignore that error and continue on.
            not_received=[],
        )

        # Starting the session should close successfully and report the busy state
        backend.put_task(tasks.START_SESSION_TASK)
        assert_messages(
            backend,
            received=[
                PluginStateMessage(state=PluginState.LOADED_STARTING),
                PluginStateMessage(state=PluginState.LOADED_BUSY),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
        )
        # make sure NUM_CALLS_TO_REQUEST calls has been received by receiving
        # the same number of PlotMessages
        assert_num_calls(backend, NUM_CALLS_TO_REQUEST, PlotMessage)

        # Stopping the task should be successful and report the idle state
        backend.put_task(tasks.STOP_SESSION_TASK)
        assert_messages(
            backend,
            received=[
                PluginStateMessage(state=PluginState.LOADED_STOPPING),
                PluginStateMessage(state=PluginState.LOADED_IDLE),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
        )

        saved_file = t.cast(CaptureSaveableFile, backend).saveable_file_path

        with a121.open_record(saved_file) as _:
            # this open makes sure that the file can be opened directly after
            # the session is stopped
            pass

        if plugin in [SPEED_DETECTOR_PLUGIN]:
            pytest.xfail(
                "Presence- & presence-based algorithms have an "
                + "untestable 'load_from_file' task because of 'estimated_frame_rate'. "
                + "'start_session' & 'stop_session' are tested."
            )
        else:
            backend.put_task(tasks.load_from_file_task(saved_file))
            assert_messages(
                backend,
                received=[
                    PluginStateMessage(state=PluginState.LOADED_STARTING),
                    PluginStateMessage(state=PluginState.LOADED_BUSY),
                    PluginStateMessage(state=PluginState.LOADED_STOPPING),
                    PluginStateMessage(state=PluginState.LOADED_IDLE),
                    tasks.SUCCESSFULLY_CLOSED_TASK,
                ],
            )
