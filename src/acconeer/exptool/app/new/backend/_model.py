from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional, Type

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

    def idle(self) -> bool:
        if self.backend_plugin is None:
            return False

        try:
            return self.backend_plugin.idle()
        except Exception:
            log.error("Backend plugin idle failed")
            return False

    def execute_task(self, task: Task) -> bool:
        """Executes the task ``task``.

        :returns: True if it was successful (no ``Exception``s raised) else False
        """
        try:
            self._execute_task(task)
        except Exception as e:
            task_name, _ = task
            self.task_callback(ErrorMessage(task_name, e))
            log.exception(e)
            return False
        else:
            return True

    def _execute_task(self, task: Task) -> None:
        task_name, task_kwargs = task
        if task_name == "connect_client":
            self.connect_client(**task_kwargs)
        elif task_name == "disconnect_client":
            self.disconnect_client(**task_kwargs)
        elif task_name == "load_plugin":
            self.load_plugin(**task_kwargs)
        elif task_name == "unload_plugin":
            self.unload_plugin()
        elif task_name == "load_from_file":
            self.load_from_file(**task_kwargs)
        elif self.backend_plugin is not None:
            self.backend_plugin.execute_task(task=task)
        else:
            log.warning(f"Got unsupported task: {task_name}")

    def connect_client(self, client_info: a121.ClientInfo) -> None:
        """Connects the Model's client

        Callbacks:
        - ErrorMessage("connect_client") if Model already have a client.
        - ErrorMessage("connect_client") if the client cannot be connected.
        - OkMessage("connect_client") if client connected succesfully
        - DataMessage("server_info")  -||-

        :param client_info: Used to create and connect the client
        """
        if self.client is not None:
            self.task_callback(
                ErrorMessage(
                    "connect_client",
                    RuntimeError(
                        "Model already has a Client. "
                        + "The current Client needs to be disconnected first."
                    ),
                )
            )
            return

        self.client = a121.Client(
            ip_address=client_info.ip_address,
            serial_port=client_info.serial_port,
            override_baudrate=client_info.override_baudrate,
        )

        try:
            self.client.connect()
        except Exception as e:
            self.task_callback(ErrorMessage("connect_client", e))
            self.client = None
        else:
            if self.backend_plugin is not None:
                self.backend_plugin.attach_client(client=self.client)

            self.task_callback(OkMessage("connect_client"))
            self.task_callback(DataMessage("server_info", self.client.server_info))

    def disconnect_client(self) -> None:
        """Disconnects the Model's client

        Callbacks:
        - ErrorMessage("disconnect_client") if Model doesn't have a client (already disconnected).
        - OkMessage("disconnect_client") if client disconnected succesfully
        """
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
        self.client = None
        self.task_callback(OkMessage("disconnect_client"))

    def load_plugin(self, *, plugin: Type[BackendPlugin], key: str) -> None:
        """Loads a plugin

        Callbacks:
        - ErrorMessage("load_plugin") if Model already has a loaded plugin
        - OkMessage("load_plugin") if the plugin was loaded succesfully

        :param plugin: Type of ``BackendPlugin`` to load.
        """
        if self.backend_plugin is not None:
            self.task_callback(
                ErrorMessage(
                    "load_plugin",
                    RuntimeError("Cannot load a plugin. Unload the current one first"),
                )
            )
            return

        self.backend_plugin = plugin(callback=self.task_callback, key=key)
        log.info(f"{plugin.__name__} was loaded.")

        if self.client is not None and self.client.connected:
            self.backend_plugin.attach_client(client=self.client)
            log.debug(f"{plugin.__name__} was attached a Client")

        self.task_callback(OkMessage("load_plugin"))

    def unload_plugin(self) -> None:
        """Unloads a plugin.

        Callbacks:
        - OkMessage("unload_plugin") always.
        """
        if self.backend_plugin is None:
            return

        self.backend_plugin.teardown()
        self.backend_plugin = None
        log.debug("Current BackendPlugin was torn down")
        self.task_callback(OkMessage("unload_plugin"))

    def load_from_file(self, *, path: Path) -> None:
        if self.backend_plugin is None:
            raise RuntimeError("Plugin not loaded on load_from_file")

        self.backend_plugin.load_from_file(path=path)
