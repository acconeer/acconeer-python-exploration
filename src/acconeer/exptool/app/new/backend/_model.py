from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Type

from acconeer.exptool import a121
from acconeer.exptool.app.new._enums import ConnectionState, PluginState
from acconeer.exptool.app.new._exceptions import HandledException

from ._backend_plugin import BackendPlugin
from ._message import ConnectionStateMessage, GeneralMessage, Message, PluginStateMessage


log = logging.getLogger(__name__)


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

            self.backend_plugin.execute_task(name, kwargs)
            return

        if name == "connect_client":
            self.connect_client(**kwargs)
        elif name == "disconnect_client":
            self.disconnect_client(**kwargs)
        elif name == "load_plugin":
            self.load_plugin(**kwargs)
        elif name == "unload_plugin":
            self.unload_plugin(**kwargs)
        else:
            raise RuntimeError(f"Unknown task: {name}")

    def connect_client(self, client_info: a121.ClientInfo) -> None:
        if self.client is not None:
            raise RuntimeError(
                "Model already has a Client. The current Client needs to be disconnected first."
            )

        self.client = a121.Client(
            ip_address=client_info.ip_address,
            serial_port=client_info.serial_port,
            override_baudrate=client_info.override_baudrate,
        )

        try:
            self.client.connect()
        except Exception as exc:
            self.client = None
            self.task_callback(ConnectionStateMessage(state=ConnectionState.DISCONNECTED))
            raise HandledException("Failed to connect") from exc

        if self.backend_plugin is not None:
            self.backend_plugin.attach_client(client=self.client)

        self.task_callback(ConnectionStateMessage(state=ConnectionState.CONNECTED))
        self.task_callback(GeneralMessage(name="server_info", data=self.client.server_info))

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

    def load_plugin(self, *, plugin: Type[BackendPlugin], key: str) -> None:
        if self.backend_plugin is not None:
            self.unload_plugin(send_callback=False)

        self.backend_plugin = plugin(callback=self.task_callback, key=key)
        log.info(f"{plugin.__name__} was loaded.")

        if self.client is not None and self.client.connected:
            self.backend_plugin.attach_client(client=self.client)
            log.debug(f"{plugin.__name__} was attached a Client")

        self.task_callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

    def unload_plugin(self, send_callback: bool = True) -> None:
        if self.backend_plugin is None:
            return

        self.backend_plugin.teardown()
        self.backend_plugin = None
        log.debug("Current BackendPlugin was torn down")

        if send_callback:
            self.task_callback(PluginStateMessage(state=PluginState.UNLOADED))
