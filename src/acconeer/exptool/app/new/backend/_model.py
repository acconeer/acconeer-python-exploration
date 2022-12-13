# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

import packaging.version

from acconeer.exptool import a121
from acconeer.exptool.app.new._enums import ConnectionState, PluginState
from acconeer.exptool.app.new._exceptions import HandledException

from ._backend_plugin import BackendPlugin
from ._message import ConnectionStateMessage, GeneralMessage, Message, PluginStateMessage


log = logging.getLogger(__name__)


T = TypeVar("T")
MessageHandler = Callable[[Message], None]
BackendPluginFactory = Callable[[MessageHandler, str], BackendPlugin]


def is_task(func: T) -> T:
    setattr(func, "is_task", True)
    return func


class Model:
    backend_plugin: Optional[BackendPlugin]
    client: Optional[a121.Client]

    def __init__(self, task_callback: Callable[[Message], None]) -> None:
        self.backend_plugin = None
        self.client = None
        self.task_callback = task_callback

    def idle(self) -> bool:
        if self.backend_plugin is None:
            return False

        return self.backend_plugin.idle()

    def execute_task(self, name: str, kwargs: dict[str, Any], plugin: bool) -> None:
        if plugin:
            if self.backend_plugin is None:
                raise RuntimeError

            obj: Any = self.backend_plugin
        else:
            obj = self

        try:
            method = getattr(obj, name)
            if not getattr(method, "is_task"):
                raise Exception
        except Exception:
            raise RuntimeError(f"'{name}' is not a task")

        method(**kwargs)

    @is_task
    def connect_client(self, client_info: a121.ClientInfo) -> None:
        if self.client is not None:
            raise RuntimeError(
                "Model already has a Client. The current Client needs to be disconnected first."
            )

        self.client = a121.Client(
            ip_address=client_info.ip_address,
            serial_port=client_info.serial_port,
            usb_device=client_info.usb_device,
            override_baudrate=client_info.override_baudrate,
            mock=client_info.mock,
        )

        try:
            self.client.connect()
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

        ver = packaging.version.Version(a121.SDK_VERSION)
        if self.client.server_info.parsed_rss_version > ver:
            connection_warning = "New server version - please upgrade client"
        elif self.client.server_info.parsed_rss_version < ver:
            connection_warning = "Old server version - please upgrade server"
        else:
            connection_warning = None

        self.task_callback(
            ConnectionStateMessage(state=ConnectionState.CONNECTED, warning=connection_warning)
        )
        self.task_callback(GeneralMessage(name="server_info", data=self.client.server_info))

    @is_task
    def disconnect_client(self) -> None:
        if self.client is None:
            raise RuntimeError("Backend has no client to disconnect.")

        if self.backend_plugin is not None:
            self.backend_plugin.detach_client()

        try:
            self.client.disconnect()
        except Exception:
            pass

        self.client = None

        self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTED))

    @is_task
    def load_plugin(self, *, plugin_factory: BackendPluginFactory, key: str) -> None:
        if self.backend_plugin is not None:
            self.unload_plugin(send_callback=False)

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

        self.backend_plugin.teardown()
        self.backend_plugin = None
        log.debug("Current BackendPlugin was torn down")

        if send_callback:
            self.task_callback(PluginStateMessage(state=PluginState.UNLOADED))
