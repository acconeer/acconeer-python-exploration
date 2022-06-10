from __future__ import annotations

import logging
from typing import Callable, Optional

from acconeer.exptool import a121

from ._backend_plugin import BackendPlugin
from ._message import DataMessage, ErrorMessage, Message, OkMessage
from ._types import Task


log = logging.getLogger(__name__)


class Model:
    backend_plugin: Optional[BackendPlugin]
    client: Optional[a121.Client]

    def __init__(self, task_callback: Callable[[Message], None]) -> None:
        self.backend_plugin = None
        self.client = None
        self.task_callback = task_callback

    def execute_task(self, task: Task) -> None:
        try:
            self._execute_task(task)
        except Exception as e:
            task_name, _ = task
            self.task_callback(ErrorMessage(task_name, e))
            log.exception(e)

    def _execute_task(self, task: Task) -> None:
        task_name, task_kwargs = task
        if task_name == "connect_client":
            self.connect_client(**task_kwargs)
        elif task_name == "disconnect_client":
            self.disconnect_client(**task_kwargs)
        elif self.backend_plugin is not None:
            self.backend_plugin.execute_task(task=task)
        else:
            log.warning(f"Got unsupported task: {task_name}")

    def connect_client(self, client_info: a121.ClientInfo) -> None:
        if self.client is None:
            self.client = a121.Client(
                ip_address=client_info.ip_address,
                serial_port=client_info.serial_port,
                override_baudrate=client_info.override_baudrate,
            )
        elif self.client.connected:
            log.warn("Tried to connect when the Client is already connected. Will do nothing.")
            return
        elif self.backend_plugin is not None:
            self.client = a121.Client(
                ip_address=client_info.ip_address,
                serial_port=client_info.serial_port,
                override_baudrate=client_info.override_baudrate,
            )
            self.backend_plugin.attach_client(client=self.client)

        try:
            self.client.connect()
        except Exception as e:
            self.task_callback(ErrorMessage("connect_client", e))
            self.client = None
        else:
            self.task_callback(OkMessage("connect_client"))
            self.task_callback(DataMessage("server_info", self.client.server_info))

    def disconnect_client(self) -> None:
        if self.client is None:
            self.task_callback(
                ErrorMessage(
                    "disconnect_client",
                    RuntimeError("Backend has no client to disconnect."),
                )
            )
            return

        if self.backend_plugin is not None:
            self.backend_plugin.detach_client()

        self.client.disconnect()
        self.task_callback(OkMessage("disconnect_client"))

    def _load_plugin(self, *, plugin: BackendPlugin) -> None:
        self.backend_plugin = plugin
        self.backend_plugin.setup(callback=self.task_callback)
