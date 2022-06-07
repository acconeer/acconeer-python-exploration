from __future__ import annotations

import logging
from typing import Callable, Optional

from acconeer.exptool import a121

from ._backend_plugin import BackendPlugin
from ._message import Message
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
            log.exception(e)

    def _execute_task(self, task: Task) -> None:
        task_name, task_kwargs = task
        if task_name == "connect_client":
            self.connect_client(**task_kwargs)
        elif task_name == "disconnect_client":
            self.disconnect_client(**task_kwargs)
        else:
            log.warning(f"Got unsupported task: {task_name}")

    def connect_client(self, client_info: a121.ClientInfo) -> None:
        self.client = a121.Client(
            ip_address=client_info.ip_address,
            serial_port=client_info.serial_port,
            override_baudrate=client_info.override_baudrate,
        )
        try:
            self.client.connect()
        except Exception as e:
            self.task_callback(Message("error", "connect_client", e))
            self.client = None
        else:
            self.task_callback(
                Message(
                    "ok",
                    "connect_client",
                )
            )

    def disconnect_client(self) -> None:
        if self.client is None:
            self.task_callback(
                Message(
                    "error",
                    "disconnect_client",
                    RuntimeError("Backend has no client to disconnect."),
                )
            )
            return

        self.client.disconnect()
        self.client = None
        self.task_callback(Message("ok", "disconnect_client"))

    def _load_plugin(self, *, plugin: BackendPlugin) -> None:
        self.backend_plugin = plugin
        self.backend_plugin.setup(callback=self.task_callback)
