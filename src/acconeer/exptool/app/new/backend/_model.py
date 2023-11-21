# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

import packaging.version

from acconeer.exptool import _core as core
from acconeer.exptool.app.new._enums import ConnectionState, PluginState
from acconeer.exptool.app.new._exceptions import HandledException

from ._backend_plugin import BackendPlugin
from ._message import ConnectionStateMessage, GeneralMessage, Message, PluginStateMessage
from ._tasks import Task, get_task, is_task


log = logging.getLogger(__name__)


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

    def idle(self) -> bool:
        if self.backend_plugin is None:
            return False

        return self.backend_plugin.idle()

    def execute_task(self, task: Task) -> None:
        (name, kwargs) = task

        builtin_task = get_task(self, name)
        if builtin_task is not None:
            builtin_task(**kwargs)
            return

        plugin_task = get_task(self.backend_plugin, name)
        if plugin_task is not None:
            plugin_task(**kwargs)
            return

        raise RuntimeError(f"'{name}' is not a task")

    @is_task
    def connect_client(
        self,
        client_factory: Callable[[], _AnyClient],
        get_connection_warning: Callable[[packaging.version.Version], Optional[str]],
    ) -> None:
        if self.client is not None:
            raise RuntimeError(
                "Model already has a Client. The current Client needs to be disconnected first."
            )

        self.task_callback(ConnectionStateMessage(state=ConnectionState.CONNECTING))

        try:
            self.client = client_factory()
        except Exception as exc:
            self.client = None
            self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTED))

            msg = "Failed to connect"

            try:
                msg += f":\n{exc}"
            except Exception:
                pass

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
            raise RuntimeError("Backend has no client to disconnect.")

        self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTING))

        if self.backend_plugin is not None:
            self.backend_plugin.detach_client()

        try:
            self.client.close()
        except Exception:
            pass

        self.client = None

        self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTED))

    @is_task
    def load_plugin(self, *, plugin_factory: BackendPluginFactory, key: str) -> None:
        if self.backend_plugin is not None:
            self.unload_plugin(send_callback=False)

        self.task_callback(PluginStateMessage(state=PluginState.LOADING))

        self.backend_plugin = plugin_factory(self.task_callback, key)
        log.info(f"{plugin_factory.__name__} was loaded.")

        if self.client is not None and self.client.connected:
            self.backend_plugin.attach_client(client=self.client)
            log.debug(f"{plugin_factory.__name__} was attached a Client")

        self.task_callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

    @is_task
    def unload_plugin(self, send_callback: bool = True) -> None:
        if self.backend_plugin is None:
            return

        if send_callback:
            self.task_callback(PluginStateMessage(state=PluginState.UNLOADING))

        self.backend_plugin.teardown()
        self.backend_plugin = None
        log.debug("Current BackendPlugin was torn down")

        if send_callback:
            self.task_callback(PluginStateMessage(state=PluginState.UNLOADED))
