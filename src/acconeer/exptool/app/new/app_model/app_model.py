# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import logging
import queue
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, Type
from uuid import UUID

import attrs

from PySide6.QtCore import QDeadlineTimer, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QWidget

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new._enums import (
    ConnectionInterface,
    ConnectionState,
    PluginFamily,
    PluginGeneration,
    PluginState,
)
from acconeer.exptool.app.new._exceptions import HandledException
from acconeer.exptool.app.new.app_model.file_detective import investigate_file
from acconeer.exptool.app.new.backend import (
    Backend,
    BackendPlugin,
    BackendPluginStateMessage,
    ClosedTask,
    ConnectionStateMessage,
    GeneralMessage,
    Message,
    PluginStateMessage,
    StatusMessage,
)
from acconeer.exptool.app.new.storage import get_config_dir, remove_temp_dir
from acconeer.exptool.utils import USBDevice  # type: ignore[import]

from .port_updater import PortUpdater
from .rate_calc import RateCalculator


log = logging.getLogger(__name__)


class AppModelAwarePlugin:
    def __init__(self, app_model: AppModel) -> None:
        app_model.sig_notify.connect(self.on_app_model_update)

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass


class PlotPlugin(AppModelAwarePlugin, abc.ABC):
    def __init__(self, app_model: AppModel, plot_layout: pg.GraphicsLayout) -> None:
        super().__init__(app_model=app_model)
        self.plot_layout = plot_layout

        app_model.sig_message_plot_plugin.connect(self.handle_message)

    @abc.abstractmethod
    def handle_message(self, message: GeneralMessage) -> None:
        pass

    @abc.abstractmethod
    def draw(self) -> None:
        pass


class ViewPlugin(AppModelAwarePlugin, abc.ABC):
    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model)
        self.app_model = app_model
        self.view_widget = view_widget

        app_model.sig_message_view_plugin.connect(self.handle_message)

    @abc.abstractmethod
    def handle_message(self, message: GeneralMessage) -> None:
        pass


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
    sig_backend_closed_task = Signal(ClosedTask)
    sig_backend_message = Signal(Message)

    def __init__(self, backend: Backend, parent: QObject) -> None:
        super().__init__(parent)
        self.backend = backend

    def run(self) -> None:
        log.debug("Backend listening thread starting...")

        while not self.isInterruptionRequested():
            try:
                item = self.backend.recv(timeout=0.1)
            except queue.Empty:
                continue

            if isinstance(item, Message):
                self.sig_backend_message.emit(item)
            elif isinstance(item, ClosedTask):
                self.sig_backend_closed_task.emit(item)
            else:
                raise AssertionError

        log.debug("Backend listening thread stopping...")


class AppModel(QObject):
    sig_notify = Signal(object)
    sig_error = Signal(Exception, object)
    sig_load_plugin = Signal(object)
    sig_message_plot_plugin = Signal(object)
    sig_message_view_plugin = Signal(object)
    sig_status_message = Signal(object)
    sig_update_rate = Signal(float, float)

    plugins: list[Plugin]
    plugin: Optional[Plugin]

    backend_plugin_state: Any

    connection_state: ConnectionState
    connection_warning: Optional[str]
    connection_interface: ConnectionInterface
    plugin_state: PluginState
    socket_connection_ip: str
    serial_connection_port: Optional[str]
    available_tagged_ports: list[Tuple[str, Optional[str]]]
    usb_connection_device: Optional[USBDevice]
    available_usb_devices: list[USBDevice]
    saveable_file: Optional[Path]

    def __init__(self, backend: Backend, plugins: list[Plugin]) -> None:
        super().__init__()
        self._backend = backend
        self._listener = _BackendListeningThread(self._backend, self)
        self._listener.sig_backend_message.connect(self._handle_backend_message)
        self._listener.sig_backend_closed_task.connect(self._handle_backend_closed_task)
        self._port_updater = PortUpdater(self)
        self._port_updater.sig_update.connect(self._handle_port_update)

        self._backend_task_callbacks: dict[UUID, Any] = {}

        self._a121_server_info: Optional[a121.ServerInfo] = None

        self.plugins = plugins
        self.plugin = None

        self.backend_plugin_state = None

        self.connection_state = ConnectionState.DISCONNECTED
        self.connection_warning = None
        self.connection_interface = ConnectionInterface.SERIAL
        self.plugin_state = PluginState.UNLOADED
        self.socket_connection_ip = ""
        self.serial_connection_port = None
        self.usb_connection_device = None
        self.available_tagged_ports = []
        self.available_usb_devices = []
        self.saveable_file = None

        self.rate_calc = RateCalculator()

    def start(self) -> None:
        self._listener.start()
        self._port_updater.start()

    def stop(self) -> None:

        WAIT_FOR_UNLOAD_TIMEOUT = 1.0

        self.load_plugin(None)
        if self.connection_state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
            self.disconnect_client()

        wait_start_time = time.time()
        while (
            self.plugin_state != PluginState.UNLOADED
            and self.connection_state != ConnectionState.DISCONNECTED
        ):  # TODO: Do this better
            QApplication.processEvents()

            if (time.time() - wait_start_time) > WAIT_FOR_UNLOAD_TIMEOUT:
                log.error("Plugin not unloaded on stop")
                break

        remove_temp_dir()

        self._listener.requestInterruption()
        status = self._listener.wait(QDeadlineTimer(500))

        if not status:
            log.debug("Backend listening thread did not stop when requested, terminating...")
            self._listener.terminate()

        self._port_updater.stop()

    def broadcast(self) -> None:
        self.sig_notify.emit(self)

    def emit_error(self, exception: Exception, traceback_format_exc: Optional[str] = None) -> None:
        log.debug("Emitting error")
        self.sig_error.emit(exception, traceback_format_exc)

    def _put_backend_task(
        self,
        name: str,
        kwargs: Optional[dict[str, Any]] = None,
        *,
        plugin: bool = False,
        on_ok: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception, Optional[str]], None]] = None,
    ) -> None:
        if kwargs is None:
            kwargs = {}

        key = self._backend.put_task((name, kwargs, plugin))
        self._backend_task_callbacks[key] = {
            "on_ok": on_ok,
            "on_error": on_error,
        }

        log.debug(f"Put backend task with name: '{name}', key: {key.time_low}")

    def put_backend_plugin_task(
        self,
        name: str,
        kwargs: Optional[dict[str, Any]] = None,
        *,
        on_ok: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception, Optional[str]], None]] = None,
    ) -> None:
        self._put_backend_task(
            name,
            kwargs,
            plugin=True,
            on_ok=on_ok,
            on_error=on_error,
        )

    def _handle_backend_closed_task(self, closed_task: ClosedTask) -> None:
        log.debug(f"Got backend closed task: {closed_task.key.time_low}")

        callbacks = self._backend_task_callbacks.pop(closed_task.key)

        if closed_task.exception:
            f = callbacks["on_error"]
            if f:
                f(closed_task.exception, closed_task.traceback_format_exc)
        else:
            f = callbacks["on_ok"]
            if f:
                f()

    def _handle_backend_message(self, message: Message) -> None:
        if isinstance(message, ConnectionStateMessage):
            log.debug("Got backend connection state message")
            self.connection_state = message.state
            self.connection_warning = message.warning
            self.broadcast()
        elif isinstance(message, PluginStateMessage):
            log.debug("Got backend plugin state message")
            self.plugin_state = message.state
            self.broadcast()
        elif isinstance(message, BackendPluginStateMessage):
            log.debug("Got backend plugin state message")
            self.backend_plugin_state = message.state
            self.broadcast()
        elif isinstance(message, StatusMessage):
            self.send_status_message(message.status)
        elif isinstance(message, GeneralMessage):
            if message.recipient is not None:
                if message.recipient == "plot_plugin":
                    self.sig_message_plot_plugin.emit(message)
                elif message.recipient == "view_plugin":
                    self.sig_message_view_plugin.emit(message)
                else:
                    raise RuntimeError(f"Got message with unknown recipient '{message.recipient}'")
            else:
                self._handle_backend_general_message(message)
        else:
            raise RuntimeError(f"Got message of unknown type '{type(message)}'")

    def _handle_backend_general_message(self, message: GeneralMessage) -> None:
        if message.exception:
            self.emit_error(message.exception, message.traceback_format_exc)
            return

        if message.name == "server_info":
            self._a121_server_info = message.data
            self.broadcast()
        elif message.name == "serialized":
            assert message.kwargs is not None
            self._handle_backend_serialized(**message.kwargs)
        elif message.name == "saveable_file":
            assert message.data is None or isinstance(message.data, Path)
            self._update_saveable_file(message.data)
        elif message.name == "result_tick_time":
            update_time = message.data

            rate, jitter = self.rate_calc.update(update_time)
            self.sig_update_rate.emit(rate, jitter)
        else:
            raise RuntimeError(f"Got unknown general message '{message.name}'")

    @classmethod
    def _handle_backend_serialized(
        cls, *, generation: PluginGeneration, key: str, data: Optional[bytes]
    ) -> None:
        path = cls._get_plugin_config_path(generation, key)

        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def _update_saveable_file(self, path: Optional[Path]) -> None:
        if self.saveable_file is not None:
            self.saveable_file.unlink(missing_ok=True)

        self.saveable_file = path
        self.broadcast()

    @classmethod
    def _get_plugin_config_path(cls, generation: PluginGeneration, key: str) -> Path:
        return (get_config_dir() / "plugin" / generation.value / key).with_suffix(".pickle")

    def _handle_port_update(
        self,
        tagged_ports: list[Tuple[str, Optional[str]]],
        usb_devices: Optional[list[USBDevice]],
    ) -> None:
        tagged_ports_map = dict(tagged_ports)
        if self.connection_state is not ConnectionState.DISCONNECTED and (
            (
                self.connection_interface == ConnectionInterface.SERIAL
                and self.serial_connection_port not in tagged_ports_map.keys()
            )
            or (
                self.connection_interface == ConnectionInterface.USB
                and usb_devices
                and self.usb_connection_device not in usb_devices
            )
        ):
            self.disconnect_client()
        self.serial_connection_port, recognized = self._select_new_serial_port(
            dict(self.available_tagged_ports),
            tagged_ports_map,
            self.serial_connection_port,
        )

        self.available_tagged_ports = tagged_ports
        connect = False

        if recognized:
            self.set_connection_interface(ConnectionInterface.SERIAL)
            self.send_status_message(f"Recognized serial port: {self.serial_connection_port}")
            connect = True

        if usb_devices is not None:
            self.usb_connection_device, recognized = self._select_new_usb_device(
                usb_devices, self.usb_connection_device
            )

            self.available_usb_devices = usb_devices

            if recognized:
                assert self.usb_connection_device is not None
                self.set_connection_interface(ConnectionInterface.USB)
                self.send_status_message(f"Recognized USB device: {self.usb_connection_device}")
                connect = True

        if connect:
            self._autoconnect()

        self.broadcast()

    def _autoconnect(self) -> None:
        self.connect_client(auto=True)

    def _select_new_serial_port(
        self,
        old_ports: dict[str, Optional[str]],
        new_ports: dict[str, Optional[str]],
        current_port: Optional[str],
    ) -> Tuple[Optional[str], bool]:
        if self.connection_state != ConnectionState.DISCONNECTED:
            return current_port, False

        if current_port not in new_ports:  # Then find a new suitable port
            port = None

            for port, tag in new_ports.items():
                if tag:
                    return port, (current_port is None)

            return port, False

        # If we already have a tagged port, keep it
        if new_ports[current_port]:
            return current_port, False

        # If a tagged port was added, select it
        added_ports = {k: v for k, v in new_ports.items() if k not in old_ports}
        for port, tag in added_ports.items():
            if tag:
                return port, True

        return current_port, False

    def _select_new_usb_device(
        self,
        new_ports: list[USBDevice],
        current_port: Optional[USBDevice],
    ) -> Tuple[Optional[USBDevice], bool]:
        if self.connection_state != ConnectionState.DISCONNECTED:
            return current_port, False

        if not new_ports:
            return None, False

        if current_port not in new_ports:
            return new_ports[0], True

        return current_port, False

    def connect_client(self, auto: bool = False) -> None:
        if self.connection_interface == ConnectionInterface.SOCKET:
            client_info = a121.ClientInfo(ip_address=self.socket_connection_ip)
        elif self.connection_interface == ConnectionInterface.SERIAL:
            client_info = a121.ClientInfo(serial_port=self.serial_connection_port)
        elif self.connection_interface == ConnectionInterface.USB:
            client_info = a121.ClientInfo(usb_device=self.usb_connection_device)
        else:
            raise RuntimeError

        log.debug(f"Connecting client with {client_info}")

        on_error = self.emit_error
        if auto:
            on_error = self._failed_autoconnect

        self._put_backend_task(
            "connect_client",
            {"client_info": client_info},
            on_error=on_error,
        )
        self.connection_state = ConnectionState.CONNECTING
        self.connection_warning = None
        self.broadcast()

    def disconnect_client(self) -> None:
        self._put_backend_task("disconnect_client", {})
        self.connection_state = ConnectionState.DISCONNECTING
        self.connection_warning = None
        self._a121_server_info = None
        self.broadcast()

    def is_connect_ready(self) -> bool:
        return (
            (self.connection_interface == ConnectionInterface.SOCKET)
            or (
                self.connection_interface == ConnectionInterface.SERIAL
                and self.serial_connection_port is not None
            )
            or (
                self.connection_interface == ConnectionInterface.USB
                and self.usb_connection_device is not None
            )
        )

    def _failed_autoconnect(
        self, exception: Exception, traceback_format_exc: Optional[str] = None
    ) -> None:
        self.send_status_message('<p style="color: #FD5200;"><b>Failed to autoconnect</b></p>')

    def set_connection_interface(self, connection_interface: ConnectionInterface) -> None:
        self.connection_interface = connection_interface
        self.broadcast()

    def set_socket_connection_ip(self, ip: str) -> None:
        self.socket_connection_ip = ip
        self.broadcast()

    def set_serial_connection_port(self, port: Optional[str]) -> None:
        self.serial_connection_port = port
        self.broadcast()

    def set_usb_connection_port(self, port: Optional[str]) -> None:
        self.usb_connection_device = port
        self.broadcast()

    def set_plugin_state(self, state: PluginState) -> None:
        self.plugin_state = state
        self.broadcast()

    def load_plugin(self, plugin: Optional[Plugin]) -> None:
        if plugin == self.plugin:
            return

        self._update_saveable_file(None)
        self.backend_plugin_state = None

        if plugin is None:
            self._put_backend_task("unload_plugin", {}, on_error=self.emit_error)
            if self.plugin is not None:
                self.plugin_state = PluginState.UNLOADING
        else:
            self._put_backend_task(
                "load_plugin",
                {"plugin": plugin.backend_plugin, "key": plugin.key},
                on_error=self.emit_error,
            )

            config_path = self._get_plugin_config_path(plugin.generation, plugin.key)
            try:
                data = config_path.read_bytes()
            except Exception:
                pass
            else:
                self.put_backend_plugin_task("deserialize", {"data": data})

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
            self.emit_error(HandledException("Cannot load file"))
            return

        if findings.generation != PluginGeneration.A121:
            self.emit_error(HandledException("This app can currently only load A121 files"))
            return

        try:
            plugin = self._find_plugin(findings.key)
        except Exception:
            log.debug(f"Could not find plugin '{findings.key}'")

            # TODO: Don't hardcode
            plugin = self._find_plugin("sparse_iq")  # noqa: F841

        self.load_plugin(plugin)
        self.put_backend_plugin_task("load_from_file", {"path": path}, on_error=self.emit_error)
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
