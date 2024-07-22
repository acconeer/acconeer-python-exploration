# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import typing as t

import dirty_equals as de
import pytest

from acconeer.exptool.app.new import ConnectionState, PluginGeneration, PluginState
from acconeer.exptool.app.new.backend import (
    Backend,
    ConnectionStateMessage,
    MpBackend,
    PluginStateMessage,
)


@pytest.fixture(params=list(PluginGeneration))
def generation(request: pytest.FixtureRequest) -> PluginGeneration:
    gen = t.cast(PluginGeneration, request.param)

    if gen not in [PluginGeneration.A121]:
        pytest.xfail("These tests uses a mock client. Only A121 has a mock client at the moment.")
    else:
        return gen


class DisconnectedBackend:
    """Mix-in with test cases for a Backend without a client"""

    def test_connect_to_invalid_client_fails_but_updates_state_accordingly(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
        generation: PluginGeneration,
    ) -> None:
        backend.put_task(tasks.BAD_CONNECT_CLIENT_TASK[generation])
        assert_messages(
            backend,
            received=[
                ConnectionStateMessage(state=ConnectionState.CONNECTING),
                ConnectionStateMessage(state=ConnectionState.DISCONNECTED),
                tasks.FAILED_CLOSED_TASK,
            ],
            not_received=[ConnectionStateMessage(state=ConnectionState.DISCONNECTING)],
        )

    def test_connecting_to_a_valid_client_updates_state(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
        generation: PluginGeneration,
    ) -> None:
        backend.put_task(tasks.CONNECT_CLIENT_TASK[generation])
        assert_messages(
            backend,
            received=[
                ConnectionStateMessage(state=ConnectionState.CONNECTING),
                ConnectionStateMessage(state=ConnectionState.CONNECTED),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
        )

    def test_disconnecting_fails_and_does_not_update_connection_state(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        backend.put_task(tasks.DISCONNECT_CLIENT_TASK)
        assert_messages(
            backend,
            received=[tasks.FAILED_CLOSED_TASK],
            not_received=[ConnectionStateMessage(state=de.AnyThing)],
        )


class ConnectedBackend:
    """Mix-in with test cases for a Backend with a client"""

    def test_connecting_fails_and_does_not_update_connection_state(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
        generation: PluginGeneration,
    ) -> None:
        backend.put_task(tasks.CONNECT_CLIENT_TASK[generation])
        assert_messages(
            backend,
            received=[tasks.FAILED_CLOSED_TASK],
            not_received=[ConnectionStateMessage(state=de.AnyThing)],
        )

    def test_can_disconnect_its_client(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        backend.put_task(tasks.DISCONNECT_CLIENT_TASK)
        assert_messages(
            backend,
            received=[
                ConnectionStateMessage(state=ConnectionState.DISCONNECTING),
                ConnectionStateMessage(state=ConnectionState.DISCONNECTED),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
        )


class UnloadedBackend:
    """Mix-in with test cases for a Backend without a plugin"""

    def test_loading_a_plugin_reports_loading_and_loaded_plugin_state(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        backend.put_task(tasks.LOAD_PLUGIN_TASK)
        assert_messages(
            backend,
            received=[
                PluginStateMessage(state=PluginState.LOADING),
                PluginStateMessage(state=PluginState.LOADED_IDLE),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
        )

    def test_unloading_nonexisting_plugin_is_allowed_but_does_not_change_state(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        backend.put_task(tasks.UNLOAD_PLUGIN_TASK)
        assert_messages(
            backend,
            received=[tasks.SUCCESSFULLY_CLOSED_TASK],
            not_received=[PluginStateMessage(state=de.AnyThing)],
        )


class LoadedBackend:
    """Mix-in with test cases for a Backend with a plugin"""

    def test_loading_a_plugin_does_not_report_any_unloading_state_changes(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        backend.put_task(tasks.LOAD_PLUGIN_TASK)
        assert_messages(
            backend,
            received=[
                PluginStateMessage(state=PluginState.LOADING),
                PluginStateMessage(state=PluginState.LOADED_IDLE),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
            not_received=[
                PluginStateMessage(state=PluginState.UNLOADING),
                PluginStateMessage(state=PluginState.UNLOADED),
            ],
        )

    def test_unloading_plugin_updates_state(
        self,
        backend: Backend,
        assert_messages: t.Callable[..., None],
        tasks: t.Any,
    ) -> None:
        backend.put_task(tasks.UNLOAD_PLUGIN_TASK)
        assert_messages(
            backend,
            received=[
                PluginStateMessage(state=PluginState.UNLOADING),
                PluginStateMessage(state=PluginState.UNLOADED),
                tasks.SUCCESSFULLY_CLOSED_TASK,
            ],
        )


class TestDisconnectedUnloadedBackend(DisconnectedBackend, UnloadedBackend):
    """Tests that define the behaviour of Backend
    when it does not have a connected client or a plugin loaded
    """

    @pytest.fixture
    def backend(self) -> t.Iterator[Backend]:
        b = MpBackend()
        b.start()
        yield b
        b.stop()


class TestConnectedUnloadedBackend(ConnectedBackend, UnloadedBackend):
    """Tests that define the behaviour of Backend
    when it has a connected client but not a plugin loaded
    """

    @pytest.fixture
    def backend(
        self, tasks: t.Any, assert_messages: t.Callable[..., None], generation: PluginGeneration
    ) -> t.Iterator[Backend]:
        b = MpBackend()
        b.start()
        b.put_task(tasks.CONNECT_CLIENT_TASK[generation])
        assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])
        yield b
        b.stop()


class TestDisconnectedLoadedBackend(DisconnectedBackend, LoadedBackend):
    """Tests that define the behaviour of Backend
    when it does not have a connected client but has a plugin loaded
    """

    @pytest.fixture
    def backend(self, tasks: t.Any, assert_messages: t.Callable[..., None]) -> t.Iterator[Backend]:
        b = MpBackend()
        b.start()
        b.put_task(tasks.LOAD_PLUGIN_TASK)
        assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])
        yield b
        b.stop()


class TestConnectedLoadedBackend(ConnectedBackend, LoadedBackend):
    """Tests that define the behaviour of Backend
    when it has a both a connected client and a plugin loaded
    """

    @pytest.fixture
    def backend(
        self, tasks: t.Any, assert_messages: t.Callable[..., None], generation: PluginGeneration
    ) -> t.Iterator[Backend]:
        b = MpBackend()
        b.start()
        b.put_task(tasks.CONNECT_CLIENT_TASK[generation])
        assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])
        b.put_task(tasks.LOAD_PLUGIN_TASK)
        assert_messages(b, received=[tasks.SUCCESSFULLY_CLOSED_TASK])
        yield b
        b.stop()
