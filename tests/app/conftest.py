# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import copy
import functools
import queue
import typing as t
from pathlib import Path
from unittest.mock import Mock

import dirty_equals as de
import pytest

from acconeer.exptool import a121
from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new.app_model import PluginSpec
from acconeer.exptool.app.new.backend import Backend, ClosedTask, Message, Task


def _mock_plugin_factory(*args: t.Any, **kwargs: t.Any) -> t.Any:
    return Mock()


def always_return_none(*args: t.Any, **kwargs: t.Any) -> t.Any:
    return None


class Tasks:
    CONNECT_CLIENT_TASK: dict[PluginGeneration, Task] = {
        PluginGeneration.A121: (
            "connect_client",
            dict(
                client_factory=functools.partial(a121.Client.open, mock=True),
                get_connection_warning=always_return_none,
            ),
        ),
    }
    BAD_CONNECT_CLIENT_TASK = {
        PluginGeneration.A121: (
            "connect_client",
            dict(
                client_factory=functools.partial(a121.Client.open, ip_address="some_ip"),
                get_connection_warning=always_return_none,
            ),
        ),
    }
    DISCONNECT_CLIENT_TASK: Task = ("disconnect_client", {})
    LOAD_PLUGIN_TASK: Task = (
        "load_plugin",
        dict(plugin_factory=_mock_plugin_factory, key="key"),
    )
    UNLOAD_PLUGIN_TASK: Task = ("unload_plugin", {})
    START_SESSION_TASK: Task = ("start_session", dict(with_recorder=True))
    STOP_SESSION_TASK: Task = ("stop_session", {})
    CALIBRATE_DETECTOR_TASK: Task = ("calibrate_detector", {})

    SUCCESSFULLY_CLOSED_TASK = ClosedTask(
        key=de.IsUUID,
        exception=None,
        traceback_format_exc=None,
    )
    FAILED_CLOSED_TASK = ClosedTask(
        key=de.IsUUID,
        exception=de.IsInstance(Exception),
        traceback_format_exc=de.IsStr,
    )
    ANY_CLOSED_TASK = ClosedTask(
        key=de.IsUUID,
        exception=de.AnyThing,
        traceback_format_exc=de.AnyThing,
    )

    @staticmethod
    def load_from_file_task(path: Path) -> Task:
        return (
            "load_from_file",
            dict(path=path),
        )

    @staticmethod
    def load_plugin_task(spec: PluginSpec) -> Task:
        return (
            "load_plugin",
            dict(
                plugin_factory=spec.create_backend_plugin,
                key=spec.key,
            ),
        )


@pytest.fixture
def tasks() -> t.Type[Tasks]:
    return Tasks


@pytest.fixture
def assert_messages() -> t.Callable[..., None]:
    """Fixture that returns a function that may assert that messages are received from Backend"""

    def f(
        backend: Backend,
        *,
        received: list[t.Union[Message, ClosedTask]],
        not_received: t.Iterable[t.Union[Message, ClosedTask]] = tuple(),
        max_num_messages: int = 10,
        recv_timeout: float = 2.0,
    ) -> None:
        """
        Utility function that asserts that
        - certain messages were sent from Backend (received)
        - certain messages where NOT sent from Backend (not_received)

        The messages are fetched with a timeout of BACKEND_RECEIVE_TIMEOUT.
        If any receive from Backend times out, checking will be terminated.
        """
        not_yet_seen_messages = copy.deepcopy(received)
        received_messages: list[t.Union[Message, ClosedTask]] = []
        message_generator = (backend.recv(recv_timeout) for _ in range(max_num_messages))
        while not_yet_seen_messages != []:
            try:
                received_message = next(message_generator)
                received_messages.append(received_message)
            except (queue.Empty, StopIteration):
                # next(message_generator) timed out <-> message was (probably) not sent
                raise AssertionError(
                    "Did not find the messages:\n"
                    + "\n".join(f"- {m}" for m in not_yet_seen_messages)
                    + "\n"
                    + "in the received messages:\n"
                    + "\n".join(f"- {m}" for m in received_messages)
                    + "\n"
                )

            if received_message in not_received:
                raise AssertionError(f"Found message {received_message}")

            if received_message in not_yet_seen_messages:
                not_yet_seen_messages.remove(received_message)

    return f
