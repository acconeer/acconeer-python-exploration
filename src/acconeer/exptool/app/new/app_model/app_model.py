from __future__ import annotations

import abc
import logging
import queue
import shutil
from pathlib import Path
from typing import Any, Optional, Tuple, Type

import attrs

from PySide6.QtCore import QDeadlineTimer, QObject, QThread, Signal
from PySide6.QtWidgets import QWidget

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new.app_model.file_detective import investigate_file
from acconeer.exptool.app.new.backend import (
    Backend,
    BackendPlugin,
    BackendPluginStateMessage,
    BusyMessage,
    Command,
    IdleMessage,
    Message,
    Task,
)
from acconeer.exptool.app.new.storage import remove_temp_dir

from .plugin_enums import PluginFamily, PluginGeneration
from .serial_port_updater import SerialPortUpdater
from .state_enums import ConnectionInterface, ConnectionState, PluginState


log = logging.getLogger(__name__)


class AppModelAware:
    def __init__(self, app_model: AppModel) -> None:
        app_model.sig_notify.connect(self.on_app_model_update)
        app_model.sig_error.connect(self.on_app_model_error)

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_app_model_error(self, exception: Exception, traceback_str: Optional[str]) -> None:
        pass


class PlotPlugin(AppModelAware, abc.ABC):
    def __init__(self, app_model: AppModel, plot_layout: pg.GraphicsLayout) -> None:
        super().__init__(app_model=app_model)
        self.plot_layout = plot_layout

        app_model.sig_message_plot_plugin.connect(self.handle_message)

    @abc.abstractmethod
    def handle_message(self, message: Message) -> None:
        pass

    @abc.abstractmethod
    def draw(self) -> None:
        pass


class ViewPlugin(AppModelAware, abc.ABC):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model)
        self.app_model = app_model
        self.view_widget = view_widget

        app_model.sig_message_view_plugin.connect(self.handle_message)

    @abc.abstractmethod
    def handle_message(self, message: Message) -> None:
        pass

    def send_backend_command(self, command: Command) -> None:
        self.app_model._backend._send(command)

    def send_backend_task(self, task: Task) -> None:
        self.send_backend_command(("task", task))


@attrs.frozen(kw_only=True)
class Plugin:
    generation: PluginGeneration = attrs.field()
    key: str = attrs.field()
    title: str = attrs.field()
    description: Optional[str] = attrs.field(default=None)
    family: PluginFamily = attrs.field()
    backend_plugin: Type[BackendPlugin] = attrs.field()
    plot_plugin: Type[PlotPlugin] = attrs.field()
    view_plugin: Type[ViewPlugin] = attrs.field()


class _BackendListeningThread(QThread):
    sig_received_from_backend = Signal(Message)

    def __init__(self, backend: Backend, parent: QObject) -> None:
        super().__init__(parent)
        self.backend = backend

    def run(self) -> None:
        log.debug("Backend listening thread starting...")

        while not self.isInterruptionRequested():
            try:
                message = self.backend.recv(timeout=0.1)
            except queue.Empty:
                continue
            else:
                self.sig_received_from_backend.emit(message)

        log.debug("Backend listening thread stopping...")


class AppModel(QObject):
    sig_notify = Signal(object)
    sig_error = Signal(Exception, object)
    sig_load_plugin = Signal(object)
    sig_message_plot_plugin = Signal(object)
    sig_message_view_plugin = Signal(object)
    sig_status_message = Signal(object)

    plugins: list[Plugin]
    plugin: Optional[Plugin]

    backend_plugin_state: Any

    connection_state: ConnectionState
    connection_interface: ConnectionInterface
    plugin_state: PluginState
    socket_connection_ip: str
    serial_connection_port: Optional[str]
    available_tagged_ports: list[Tuple[str, Optional[str]]]
    saveable_file: Optional[Path]

    def __init__(self, backend: Backend, plugins: list[Plugin]) -> None:
        super().__init__()
        self._backend = backend
        self._listener = _BackendListeningThread(self._backend, self)
        self._listener.sig_received_from_backend.connect(self._handle_backend_message)
        self._serial_port_updater = SerialPortUpdater(self)
        self._serial_port_updater.sig_update.connect(self._handle_serial_port_update)

        self._a121_server_info: Optional[a121.ServerInfo] = None

        self.plugins = plugins
        self.plugin = None

        self.backend_plugin_state = None

        self.connection_state = ConnectionState.DISCONNECTED
        self.connection_interface = ConnectionInterface.SERIAL
        self.plugin_state = PluginState.UNLOADED
        self.socket_connection_ip = ""
        self.serial_connection_port = None
        self.available_tagged_ports = []
        self.saveable_file = None

    def start(self) -> None:
        self._listener.start()
        self._serial_port_updater.start()

    def stop(self) -> None:
        remove_temp_dir()

        self._listener.requestInterruption()
        status = self._listener.wait(QDeadlineTimer(500))

        if not status:
            log.debug("Backend listening thread did not stop when requested, terminating...")
            self._listener.terminate()

        self._serial_port_updater.stop()

    def broadcast(self) -> None:
        self.sig_notify.emit(self)

    def _handle_backend_message(self, message: Message) -> None:
        if message.status == "error":
            self.sig_error.emit(message.exception, message.traceback_str)

        if message.recipient is not None:
            if message.recipient == "plot_plugin":
                self.sig_message_plot_plugin.emit(message)
            elif message.recipient == "view_plugin":
                self.sig_message_view_plugin.emit(message)
            else:
                raise RuntimeError(
                    f"AppModel cannot handle messages with recipient {message.recipient!r}"
                )

            return

        if message.command_name == "connect_client":
            if message.status == "ok":
                self.connection_state = ConnectionState.CONNECTED
            else:
                self.connection_state = ConnectionState.DISCONNECTED
        elif message.command_name == "disconnect_client":
            if message.status == "ok":
                self.connection_state = ConnectionState.DISCONNECTED
                self._a121_server_info = None
            else:
                self.connection_state = ConnectionState.CONNECTED
        elif message.command_name == "server_info":
            self._a121_server_info = message.data
        elif message.command_name == "load_plugin":
            if message.status == "ok":
                self.plugin_state = PluginState.LOADED_IDLE
            else:
                self.plugin_state = PluginState.UNLOADED
        elif message.command_name == "unload_plugin":
            if message.status == "ok":
                self.plugin_state = PluginState.UNLOADED
            else:
                self.plugin_state = PluginState.LOADED_IDLE
        elif message.command_name == "saveable_file":
            assert message.data is None or isinstance(message.data, Path)

            if self.saveable_file is not None:
                self.saveable_file.unlink(missing_ok=True)

            self.saveable_file = message.data
        elif isinstance(message, BackendPluginStateMessage):
            log.debug("AppModel received backend plugin state")
            self.backend_plugin_state = message.data
        elif message == BusyMessage():
            self.plugin_state = PluginState.LOADED_BUSY
        elif message == IdleMessage():
            self.plugin_state = PluginState.LOADED_IDLE
        elif message.command_name == "status":
            self.send_status_message(message.data)
        elif message.command_name == "start_session":
            pass  # TODO: Should this be handled
        else:
            raise RuntimeError(f"AppModel cannot handle message: {message}")

        self.broadcast()

    def _handle_serial_port_update(self, tagged_ports: list[Tuple[str, Optional[str]]]) -> None:
        self.serial_connection_port = self._select_new_serial_port(
            dict(self.available_tagged_ports),
            dict(tagged_ports),
            self.serial_connection_port,
        )
        self.available_tagged_ports = tagged_ports

        self.broadcast()

    def _select_new_serial_port(
        self,
        old_ports: dict[str, Optional[str]],
        new_ports: dict[str, Optional[str]],
        current_port: Optional[str],
    ) -> Optional[str]:
        if self.connection_state != ConnectionState.DISCONNECTED:
            return current_port

        if current_port not in new_ports:  # Then find a new suitable port
            port = None

            for port, tag in new_ports.items():
                if tag:
                    return port

            return port

        # If we already have a tagged port, keep it
        if new_ports[current_port]:
            return current_port

        # If a tagged port was added, select it
        added_ports = {k: v for k, v in new_ports.items() if k not in old_ports}
        for port, tag in added_ports.items():
            if tag:
                return port

        return current_port

    def connect_client(self) -> None:
        if self.connection_interface == ConnectionInterface.SOCKET:
            client_info = a121.ClientInfo(ip_address=self.socket_connection_ip)
        elif self.connection_interface == ConnectionInterface.SERIAL:
            client_info = a121.ClientInfo(serial_port=self.serial_connection_port)
        else:
            raise RuntimeError

        log.debug(f"Connecting client with {client_info}")

        self._backend.put_task(
            task=(
                "connect_client",
                {"client_info": client_info},
            )
        )
        self.connection_state = ConnectionState.CONNECTING
        self.broadcast()

    def disconnect_client(self) -> None:
        self._backend.put_task(task=("disconnect_client", {}))
        self.connection_state = ConnectionState.DISCONNECTING
        self.broadcast()

    def set_connection_interface(self, connection_interface: ConnectionInterface) -> None:
        self.connection_interface = connection_interface
        self.broadcast()

    def set_socket_connection_ip(self, ip: str) -> None:
        self.socket_connection_ip = ip
        self.broadcast()

    def set_serial_connection_port(self, port: Optional[str]) -> None:
        self.serial_connection_port = port
        self.broadcast()

    def set_plugin_state(self, state: PluginState) -> None:
        self.plugin_state = state
        self.broadcast()

    def load_plugin(self, plugin: Optional[Plugin]) -> None:
        if plugin == self.plugin:
            return

        self.backend_plugin_state = None

        if plugin is None:
            self._backend.unload_plugin()
            if self.plugin is not None:
                self.plugin_state = PluginState.UNLOADING
        else:
            self._backend.load_plugin(plugin.backend_plugin, plugin.key)
            if self.plugin is not None:
                self.plugin_state = PluginState.LOADING

        self.sig_load_plugin.emit(plugin)
        self.plugin = plugin
        self.broadcast()

    def save_to_file(self, path: Path) -> None:
        log.debug(f"{self.__class__.__name__} saving to file '{path}'")

        if self.saveable_file is None:
            raise RuntimeError

        shutil.copyfile(self.saveable_file, path)

    def load_from_file(self, path: Path) -> None:
        log.debug(f"{self.__class__.__name__} loading from file '{path}'")

        findings = investigate_file(path)

        if findings is None:
            self.sig_error.emit(Exception("Cannot load file"), None)
            return

        if findings.generation != PluginGeneration.A121:
            self.sig_error.emit(Exception("This app can currently only load A121 files"), None)
            return

        try:
            plugin = self._find_plugin(findings.key)
        except Exception:
            log.debug(f"Could not find plugin '{findings.key}'")

            # TODO: Don't hardcode
            plugin = self._find_plugin("sparse_iq")  # noqa: F841

        self.load_plugin(plugin)
        self._backend.put_task(task=("load_from_file", {"path": path}))
        self.plugin_state = PluginState.LOADED_STARTING
        self.broadcast()

    def _find_plugin(self, find_key: Optional[str]) -> Plugin:  # TODO: Also find by generation
        if find_key is None:
            raise Exception

        return next(plugin for plugin in self.plugins if plugin.key == find_key)

    @property
    def rss_version(self) -> Optional[str]:
        if self._a121_server_info is None:
            return None

        return self._a121_server_info.rss_version

    def send_status_message(self, message: Optional[str]) -> None:
        self.sig_status_message.emit(message)
