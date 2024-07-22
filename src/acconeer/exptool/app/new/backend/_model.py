# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import contextlib
import time
from typing import Any, Callable, Iterator, Optional, TypeVar

import packaging.version

from acconeer.exptool import _core as core
from acconeer.exptool.app.new._enums import ConnectionState, PluginState
from acconeer.exptool.app.new._exceptions import HandledException

from ._backend_logger import BackendLogger
from ._backend_plugin import BackendPlugin
from ._message import (
    ConnectionStateMessage,
    GeneralMessage,
    Message,
    PluginStateMessage,
    TimingMessage,
)
from ._tasks import Task, get_task, get_task_names, is_task


_AnyClient = core.Client[Any, Any, Any, Any, Any]


T = TypeVar("T")
MessageHandler = Callable[[Message], None]
BackendPluginFactory = Callable[[MessageHandler, str], BackendPlugin[Any]]


class Model:
    backend_plugin: Optional[BackendPlugin[Any]]
    client: Optional[_AnyClient]

    def __init__(self, task_callback: Callable[[Message], None]) -> None:
        self.backend_plugin = None
        self.client = None
        self.task_callback = task_callback
        self._logger = BackendLogger.getLogger(__name__)

    def idle(self) -> bool:
        if self.backend_plugin is None:
            return False

        backend_plugin_class_name = type(self.backend_plugin).__name__
        with self.report_timing(f"{backend_plugin_class_name}.idle()"):
            return self.backend_plugin.idle()

    def execute_task(self, task: Task) -> None:
        (name, kwargs) = task

        builtin_task = get_task(self, name)
        if builtin_task is not None:
            with self.report_timing(f"Backend.{name}()"):
                builtin_task(**kwargs)
            return

        if self.backend_plugin is not None:
            backend_plugin_class_name = type(self.backend_plugin).__name__
            plugin_task = get_task(self.backend_plugin, name)
            if plugin_task is not None:
                with self.report_timing(f"{backend_plugin_class_name}.{name}()"):
                    plugin_task(**kwargs)
                return

        defined_tasks = get_task_names(self.backend_plugin) + get_task_names(self)
        task_list = ", ".join(defined_tasks)
        msg = f"'{name}' is not a task. Available tasks are: {task_list}."
        raise RuntimeError(msg)

    @contextlib.contextmanager
    def report_timing(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        yield
        end = time.perf_counter()
        self.task_callback(TimingMessage(name=name, start=start, end=end))

    @is_task
    def connect_client(
        self,
        client_factory: Callable[[], _AnyClient],
        get_connection_warning: Callable[[packaging.version.Version], Optional[str]],
    ) -> None:
        if self.client is not None:
            msg = "Model already has a Client. The current Client needs to be disconnected first."
            raise RuntimeError(msg)

        self.task_callback(ConnectionStateMessage(state=ConnectionState.CONNECTING))

        try:
            self.client = client_factory()
        except Exception as exc:
            self.client = None
            self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTED))

            msg = f"Failed to connect:\n{exc}"
            raise HandledException(msg)

        if self.backend_plugin is not None:
            self.backend_plugin.attach_client(client=self.client)

        self.task_callback(
            ConnectionStateMessage(
                state=ConnectionState.CONNECTED,
                warning=get_connection_warning(self.client.server_info.parsed_rss_version),
            )
        )
        self.task_callback(GeneralMessage(name="server_info", data=self.client.server_info))

    @is_task
    def disconnect_client(self) -> None:
        if self.client is None:
            msg = "Backend has no client to disconnect."
            raise RuntimeError(msg)

        self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTING))

        if self.backend_plugin is not None:
            self.backend_plugin.detach_client()

        try:
            self.client.close()
        except Exception as e:
            self._logger.exception(e)

        self.client = None

        self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTED))

    @is_task
    def load_plugin(self, *, plugin_factory: BackendPluginFactory, key: str) -> None:
        if self.backend_plugin is not None:
            self.unload_plugin(send_callback=False)

        self.task_callback(PluginStateMessage(state=PluginState.LOADING))

        self.backend_plugin = plugin_factory(self.task_callback, key)
        self._logger.info(f"{plugin_factory.__name__} was loaded.")

        if self.client is not None and self.client.connected:
            self.backend_plugin.attach_client(client=self.client)
            self._logger.debug(f"{plugin_factory.__name__} was attached a Client")

        self.task_callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

    @is_task
    def unload_plugin(self, send_callback: bool = True) -> None:
        if self.backend_plugin is None:
            return

        if send_callback:
            self.task_callback(PluginStateMessage(state=PluginState.UNLOADING))

        self.backend_plugin.teardown()
        self.backend_plugin = None
        self._logger.debug("Current BackendPlugin was torn down")

        if send_callback:
            self.task_callback(PluginStateMessage(state=PluginState.UNLOADED))
