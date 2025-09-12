# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import contextlib
import functools
import json
import logging
import queue
import shutil
import time
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from uuid import UUID

import attrs
from packaging.version import Version
from typing_extensions import Protocol

from PySide6.QtCore import QDeadlineTimer, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QWidget

from acconeer.exptool import _core as core
from acconeer.exptool import a121
from acconeer.exptool._core.communication.comm_devices import CommDevice, SerialDevice, USBDevice
from acconeer.exptool.app.new._enums import (
    ConnectionInterface,
    ConnectionState,
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
    LogMessage,
    Message,
    Model,
    PlotMessage,
    PluginStateMessage,
    StatusFileAccessMessage,
    StatusMessage,
    Task,
    TimingMessage,
    _RateStats,
)
from acconeer.exptool.app.new.storage import get_config_dir, remove_temp_dir

from .plugin_protocols import PlotPluginInterface
from .port_updater import PortUpdater


_AnyClient = core.Client[Any, Any, Any, Any, Any]
log = logging.getLogger(__name__)


class PluginPresetSpec(Protocol):
    """Defines what AppModel needs to know about a plugin preset.

    Implementations are free to add additional fields.
    """

    name: str
    description: Optional[str]
    preset_id: Enum


class PluginSpec(Protocol):
    """Defines what AppModel needs to know about a plugin.

    Implementations are free to add additional fields.
    """

    key: str
    generation: PluginGeneration
    presets: List[PluginPresetSpec]
    title: str
    default_preset_id: Enum

    def create_backend_plugin(
        self, callback: Callable[[Message], None], key: str
    ) -> BackendPlugin[Any]: ...

    def create_view_plugin(self, app_model: AppModel) -> QWidget: ...

    def create_plot_plugin(self, app_model: AppModel) -> PlotPluginInterface: ...


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


def _to_usbdevice(obj: Union[dict[str, Any], USBDevice]) -> Optional[USBDevice]:
    if isinstance(obj, dict):
        return USBDevice.from_dict(obj)
    return obj


def _to_serialdevice(obj: Union[dict[str, Any], SerialDevice]) -> Optional[SerialDevice]:
    if isinstance(obj, dict):
        return SerialDevice.from_dict(obj)
    return obj


@attrs.mutable(kw_only=True)
class _PersistentState:
    _FILE_NAME = "app_model_state.json"
    _ENUMS = {
        "ConnectionInterface": ConnectionInterface,
        "PluginGeneration": PluginGeneration,
    }

    class Encoder(json.JSONEncoder):
        def default(self, obj: Any) -> Any:
            if type(obj) in _PersistentState._ENUMS.values():
                # An enum existing in _ENUMS will be transformed to:
                # {"__enum__": "RegisteredEnum.MEMBER"}
                return {"__enum__": str(obj)}
            return json.JSONEncoder.default(self, obj)

    @staticmethod
    def _to_enum(d: dict[str, Any]) -> Any:
        if "__enum__" in d:
            # Transform the dict {"__enum__": "RegisteredEnum.MEMBER"}
            # to the enum RegisteredEnum.MEMBER
            name, member = d["__enum__"].split(".")
            return getattr(_PersistentState._ENUMS[name], member)
        return d

    connection_interface: ConnectionInterface = attrs.field(default=ConnectionInterface.SERIAL)
    plugin_generation: PluginGeneration = attrs.field(default=PluginGeneration.A121)
    socket_connection_ip: str = attrs.field(default="")
    serial_connection_device: Optional[SerialDevice] = attrs.field(
        default=None, converter=_to_serialdevice
    )
    usb_connection_device: Optional[USBDevice] = attrs.field(default=None, converter=_to_usbdevice)
    overridden_baudrate: Optional[int] = attrs.field(default=None)
    autoconnect_enabled: bool = attrs.field(default=False)
    flow_control_enabled: bool = attrs.field(default=True)
    recording_enabled: bool = attrs.field(default=True)

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> _PersistentState:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=self.Encoder)

    @classmethod
    def from_json(cls, json_str: str) -> _PersistentState:
        return cls.from_dict(json.loads(json_str, object_hook=_PersistentState._to_enum))

    @classmethod
    def from_config_file(cls) -> _PersistentState:
        return cls.from_json((get_config_dir() / cls._FILE_NAME).read_text(encoding="utf-8"))

    def to_config_file(self) -> None:
        (get_config_dir() / _PersistentState._FILE_NAME).write_text(
            self.to_json(), encoding="utf-8"
        )


class AppModel(QObject):
    sig_notify = Signal(object)
    sig_error = Signal(Exception, object)
    sig_load_plugin = Signal(object)
    sig_message_plot_plugin = Signal(PlotMessage)
    sig_message_view_plugin = Signal(object)
    sig_status_file_path = Signal(str, bool)
    sig_status_message = Signal(object)
    sig_rate_stats = Signal(float, bool, float, bool)
    sig_backend_cpu_percent = Signal(int)
    sig_frame_count = Signal(object)
    sig_backend_state_changed = Signal(object)
    sig_resource_tab_input_block_requested = Signal(object)
    """Emit a config object to spawn an input block in the resource tab"""
    sig_timing = Signal(tuple)
    """Signals the elapsed time of different things: tuple[<name>, <start time (s)>, <end time (s)>]"""

    plugins: list[PluginSpec]
    plugin: Optional[PluginSpec]

    backend_plugin_state: Any

    connection_warning: Optional[str]
    available_serial_devices: List[SerialDevice]
    available_usb_devices: List[USBDevice]

    saveable_file: Optional[Path]

    def __init__(
        self,
        backend: Backend,
        plugins: list[PluginSpec],
        force_autoconnect: bool = False,
        socket_autoconnect: Optional[str] = None,
        simulated_autocconnect: bool = False,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._listener = _BackendListeningThread(self._backend, self)
        self._listener.sig_backend_message.connect(self._handle_backend_message)
        self._listener.sig_backend_closed_task.connect(self._handle_backend_closed_task)
        self._port_updater = PortUpdater(self)
        self._port_updater.sig_update.connect(self._handle_port_update)

        self._backend_task_callbacks: dict[UUID, Any] = {}
        self._backend_task_send_timestamps: dict[UUID, float] = {}
        self._force_autoconnect = force_autoconnect

        self._a121_server_info: Optional[a121.ServerInfo] = None

        try:
            self._persistent_state = _PersistentState.from_config_file()
        except Exception as exc:
            if not isinstance(exc, FileNotFoundError):
                log.error("Config file loading failed, using defaults")
            self._persistent_state = _PersistentState()

        self.plugins = plugins
        self.plugin = None

        self.backend_plugin_state = None

        self._connection_state = ConnectionState.DISCONNECTED
        self.connection_warning = None
        self._plugin_state = PluginState.UNLOADED
        self._serial_connection_device: Optional[SerialDevice] = None
        self._usb_connection_device: Optional[USBDevice] = None
        self.available_serial_devices = []
        self.available_usb_devices = []

        self.saveable_file = None

        if socket_autoconnect is not None:
            self.set_connection_interface(ConnectionInterface.SOCKET)
            self.set_socket_connection_ip(socket_autoconnect)
            self.connect_client(auto=True)

        if simulated_autocconnect:
            self.set_connection_interface(ConnectionInterface.SIMULATED)
            self.connect_client(auto=True)

    @contextlib.contextmanager
    def report_timing(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        yield
        end = time.perf_counter()
        self.sig_timing.emit((name, start, end))

    @property
    def plugin_state(self) -> PluginState:
        """Read-only property of the plugin state"""
        return self._plugin_state

    @property
    def connection_state(self) -> ConnectionState:
        """Read-only property of the connection state"""
        return self._connection_state

    def start(self) -> None:
        self._listener.start()
        self.port_updater_enable(True)

    def stop(self) -> None:
        WAIT_FOR_UNLOAD_TIMEOUT = 1.0

        try:
            self._persistent_state.to_config_file()
        except Exception:
            log.error("Config saving failed")

        self.load_plugin(None)
        if self.connection_state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
            self.disconnect_client()

        wait_start_time = time.monotonic()
        while (
            self.plugin_state != PluginState.UNLOADED
            and self.connection_state != ConnectionState.DISCONNECTED
        ):  # TODO: Do this better
            QApplication.processEvents()

            if (time.monotonic() - wait_start_time) > WAIT_FOR_UNLOAD_TIMEOUT:
                log.error("Plugin not unloaded on stop")
                break

        remove_temp_dir()

        self._listener.requestInterruption()
        status = self._listener.wait(QDeadlineTimer(500))

        if not status:
            log.debug("Backend listening thread did not stop when requested, terminating...")
            self._listener.terminate()

        self.port_updater_enable(False)

    def broadcast(self) -> None:
        self.sig_notify.emit(self)

    def broadcast_backend_state(self) -> None:
        self.sig_backend_state_changed.emit(self.backend_plugin_state)

    def emit_error(self, exception: Exception, traceback_format_exc: Optional[str] = None) -> None:
        log.debug("Emitting error")
        self.sig_error.emit(exception, traceback_format_exc)

    def put_task(
        self,
        task: Task,
        *,
        on_ok: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception, Optional[str]], None]] = None,
    ) -> None:
        key = self._backend.put_task(task)
        self._backend_task_callbacks[key] = {
            "on_ok": on_ok,
            "on_error": on_error or self.emit_error,
        }
        self._backend_task_send_timestamps[key] = time.perf_counter()

        (name, _) = task
        log.debug(f"Put backend task with name: '{name}', key: {key.time_low}")

    def _handle_backend_closed_task(self, closed_task: ClosedTask) -> None:
        log.debug(f"Got backend closed task: {closed_task.key.time_low}")

        callbacks = self._backend_task_callbacks.pop(closed_task.key)
        task_send_timestamp = self._backend_task_send_timestamps.pop(closed_task.key)
        task_roundtrip = ("Task Roundtrip", task_send_timestamp, time.perf_counter())
        self.sig_timing.emit(task_roundtrip)

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
            log.debug(f"Got backend connection state message {message.state}")
            self.set_connection_state(message.state)
            self.connection_warning = message.warning
            self.broadcast()
        elif isinstance(message, PluginStateMessage):
            log.debug(f"Got plugin state message {message.state}")
            self._plugin_state = message.state
            self.broadcast()
        elif isinstance(message, BackendPluginStateMessage):
            log.debug("Got backend plugin state message")
            self.backend_plugin_state = message.state
            self.broadcast_backend_state()
            self.broadcast()
        elif isinstance(message, StatusFileAccessMessage):
            self.send_status_file_path(message.file_path, message.opened)
        elif isinstance(message, StatusMessage):
            self.send_status_message(message.status)
        elif isinstance(message, LogMessage):
            module_logger = logging.getLogger(message.module_name)
            loglevel_to_logfunc = {
                "CRITICAL": module_logger.critical,
                "ERROR": module_logger.error,
                "WARNING": module_logger.warning,
                "INFO": module_logger.info,
                "DEBUG": module_logger.debug,
            }
            loglevel_to_logfunc[message.log_level](message.log_string)
        elif isinstance(message, GeneralMessage):
            if message.recipient is not None:
                if message.recipient == "plot_plugin":
                    self.sig_message_plot_plugin.emit(message)
                elif message.recipient == "view_plugin":
                    self.sig_message_view_plugin.emit(message)
                else:
                    msg = f"Got message with unknown recipient '{message.recipient}'"
                    raise RuntimeError(msg)
            else:
                self._handle_backend_general_message(message)
        elif isinstance(message, TimingMessage):
            self.sig_timing.emit((message.name, message.start, message.end))
        else:
            msg = f"Got message of unknown type '{type(message)}'"
            raise RuntimeError(msg)

    def _handle_backend_general_message(self, message: GeneralMessage) -> None:
        if message.exception:
            self.emit_error(message.exception, message.traceback_format_exc)
            return

        if message.name == "server_info":
            server_info = message.data
            if isinstance(server_info, a121.ServerInfo):
                self._a121_server_info = server_info
            else:
                msg = f"Unexpected server_info type: {type(server_info)}"
                raise TypeError(msg)

            self.broadcast()
        elif message.name == "saveable_file":
            assert message.data is None or isinstance(message.data, Path)
            self._update_saveable_file(message.data)
        elif message.name == "rate_stats":
            stats = message.data
            if stats is None:
                stats = _RateStats.invalid()
            else:
                assert isinstance(stats, _RateStats)

            self.sig_rate_stats.emit(
                stats.rate,
                stats.rate_warning,
                stats.jitter,
                stats.jitter_warning,
            )
        elif message.name == "cpu_percent":
            self.sig_backend_cpu_percent.emit(message.data)
        elif message.name == "frame_count":
            self.sig_frame_count.emit(message.data)
        else:
            msg = f"Got unknown general message '{message.name}'"
            raise RuntimeError(msg)

    def _update_saveable_file(self, path: Optional[Path]) -> None:
        if self.saveable_file is not None:
            self.saveable_file.unlink(missing_ok=True)

        self.saveable_file = path
        self.broadcast()

    def _is_serial_device_unflashed(self, serial_device: Optional[SerialDevice]) -> bool:
        return bool(serial_device and serial_device.unflashed)

    def _is_usb_device_unflashed(self, usb_device: Optional[USBDevice]) -> bool:
        return bool(usb_device and usb_device.unflashed)

    def _is_usb_device_inaccessible(self, usb_device: Optional[USBDevice]) -> bool:
        return bool(usb_device and not usb_device.accessible)

    def _handle_port_update(
        self,
        serial_devices: list[SerialDevice],
        usb_devices: list[USBDevice],
    ) -> None:
        if self.connection_state is not ConnectionState.DISCONNECTED and (
            (
                self.connection_interface == ConnectionInterface.SERIAL
                and self.serial_connection_device not in serial_devices
            )
            or (
                self.connection_interface == ConnectionInterface.USB
                and self.usb_connection_device not in usb_devices
            )
        ):
            self.disconnect_client()

        first_update = len(self.available_usb_devices + self.available_serial_devices) == 0 and (
            self._persistent_state.usb_connection_device
            or self._persistent_state.serial_connection_device
        )

        serial_connection_device, recognized = self._select_new_device(
            self.available_serial_devices,
            serial_devices,
            self._persistent_state.serial_connection_device,
        )
        if serial_connection_device is None or isinstance(serial_connection_device, SerialDevice):
            self.set_serial_connection_device(serial_connection_device)
            self.available_serial_devices = serial_devices

        connect = False

        if recognized:
            self.set_connection_interface(ConnectionInterface.SERIAL)
            if self._is_serial_device_unflashed(self.serial_connection_device):
                connect = False
                self.send_warning_message(
                    f"Found unflashed device at serial port: {self.serial_connection_device}"
                )
            else:
                connect = True
                self.send_status_message(
                    f"Recognized serial port: {self.serial_connection_device}"
                )

        usb_connection_device, recognized = self._select_new_device(
            self.available_usb_devices,
            usb_devices,
            self._persistent_state.usb_connection_device,
        )
        if usb_connection_device is None or isinstance(usb_connection_device, USBDevice):
            self.set_usb_connection_device(usb_connection_device)
            self.available_usb_devices = usb_devices

        if recognized:
            assert usb_connection_device is not None
            assert isinstance(usb_connection_device, USBDevice)
            self.set_connection_interface(ConnectionInterface.USB)
            if self._is_usb_device_unflashed(usb_connection_device):
                connect = False
                self.send_warning_message(f"Found unflashed USB device: {usb_connection_device}")
            elif self._is_usb_device_inaccessible(usb_connection_device):
                connect = False
                self.send_warning_message(
                    f"Found inaccessible USB device: {usb_connection_device}"
                )
            else:
                connect = True
                self.send_status_message(f"Recognized USB device: {usb_connection_device}")

        if (
            (connect or first_update)
            and self.connection_state == ConnectionState.DISCONNECTED
            and self.autoconnect_enabled
        ):
            self._autoconnect()

        self.broadcast()

    def _autoconnect(self) -> None:
        self.connect_client(auto=True)

    def _select_new_device(
        self,
        old_devices: Sequence[CommDevice],
        new_devices: Sequence[CommDevice],
        current_port: Optional[CommDevice],
    ) -> Tuple[Optional[CommDevice], bool]:
        if self.connection_state != ConnectionState.DISCONNECTED:
            return current_port, False

        if not new_devices:
            return None, False

        added_devices = [dev for dev in new_devices if dev not in old_devices]

        # This can happen in the first port update when the current device is
        # restored from persistent state
        if current_port in added_devices:
            return current_port, False

        for device in added_devices:
            if device.recognized:
                return device, True

        if current_port not in new_devices:
            return new_devices[0], True

        return current_port, False

    def connect_client(self, auto: bool = False) -> None:
        open_client_parameters: Dict[str, Any]

        if self.connection_interface == ConnectionInterface.SIMULATED:
            open_client_parameters = {"mock": True}
        elif self.connection_interface == ConnectionInterface.SOCKET:
            open_client_parameters = {"ip_address": self.socket_connection_ip}
        elif (
            self.connection_interface == ConnectionInterface.SERIAL
            and self.serial_connection_device is not None
        ):
            open_client_parameters = {
                "serial_port": self.serial_connection_device.port,
                "override_baudrate": self.overridden_baudrate,
                "flow_control": self.flow_control_enabled,
            }
        elif (
            self.connection_interface == ConnectionInterface.USB
            and self.usb_connection_device is not None
        ):
            if self.usb_connection_device.serial is not None:
                open_client_parameters = {"usb_device": self.usb_connection_device.serial}
            else:
                open_client_parameters = {"usb_device": True}
        else:
            raise RuntimeError

        log.debug(f"Connecting client with {open_client_parameters}")

        get_connection_warning = functools.partial(
            self._connection_warning, Version(a121.SDK_VERSION)
        )
        task_putter = functools.partial(
            self.put_task,
            on_error=self._failed_autoconnect if auto else self.emit_error,
        )

        Model.connect_client.rpc(
            task_putter,
            client_factory=self._create_client_factory(
                self.plugin_generation, open_client_parameters
            ),
            get_connection_warning=get_connection_warning,
        )
        self.connection_warning = None
        self.broadcast()

    @staticmethod
    def _create_client_factory(
        generation: PluginGeneration, open_kwargs: dict[str, Any]
    ) -> Callable[[], _AnyClient]:
        factory: Callable[..., _AnyClient]
        if generation == PluginGeneration.A121:
            factory = a121.Client.open
        else:
            msg = f"Don't know how to construct a client for generation {generation}"
            raise NotImplementedError(msg)

        return functools.partial(factory, **open_kwargs)

    @staticmethod
    def _connection_warning(supported: Version, server: Version) -> Optional[str]:
        if server > supported:
            return "New server version - please upgrade client"
        elif server < supported:
            return "Old server version - please upgrade server"
        else:
            return None

    def disconnect_client(self) -> None:
        Model.disconnect_client.rpc(self.put_task)
        self.connection_warning = None
        self._a121_server_info = None
        self.broadcast()

    def is_connect_ready(self) -> bool:
        return (
            (self.connection_interface == ConnectionInterface.SOCKET)
            or (self.connection_interface == ConnectionInterface.SIMULATED)
            or (
                self.connection_interface == ConnectionInterface.SERIAL
                and self.serial_connection_device is not None
                and not self._is_serial_device_unflashed(self.serial_connection_device)
            )
            or (
                self.connection_interface == ConnectionInterface.USB
                and self.usb_connection_device is not None
                and not self._is_usb_device_unflashed(self.usb_connection_device)
                and not self._is_usb_device_inaccessible(self.usb_connection_device)
            )
        )

    def _failed_autoconnect(
        self, exception: Exception, traceback_format_exc: Optional[str] = None
    ) -> None:
        self.send_warning_message("Failed to autoconnect")

    def port_updater_enable(self, enable: bool) -> None:
        if enable:
            self._port_updater.start()
        else:
            self._port_updater.stop()

    def set_connection_state(self, new_connection_state: ConnectionState) -> None:
        if new_connection_state == ConnectionState.DISCONNECTED:
            self.port_updater_enable(True)
        else:
            self.port_updater_enable(False)
        self._connection_state = new_connection_state

    @property
    def connection_interface(self) -> ConnectionInterface:
        return self._persistent_state.connection_interface

    @property
    def socket_connection_ip(self) -> str:
        return self._persistent_state.socket_connection_ip

    @property
    def serial_connection_device(self) -> Optional[SerialDevice]:
        return self._serial_connection_device

    @property
    def usb_connection_device(self) -> Optional[USBDevice]:
        return self._usb_connection_device

    @property
    def autoconnect_enabled(self) -> bool:
        return self.autoconnect_forced or self._persistent_state.autoconnect_enabled

    @property
    def autoconnect_forced(self) -> bool:
        return self._force_autoconnect

    @property
    def flow_control_enabled(self) -> bool:
        return self._persistent_state.flow_control_enabled

    @property
    def overridden_baudrate(self) -> Optional[int]:
        return self._persistent_state.overridden_baudrate

    @property
    def recording_enabled(self) -> bool:
        return self._persistent_state.recording_enabled

    @property
    def plugin_generation(self) -> PluginGeneration:
        return self._persistent_state.plugin_generation

    def set_connection_interface(self, connection_interface: ConnectionInterface) -> None:
        self._persistent_state.connection_interface = connection_interface
        self.broadcast()

    def set_socket_connection_ip(self, ip: str) -> None:
        self._persistent_state.socket_connection_ip = ip
        self.broadcast()

    def set_serial_connection_device(self, device: Optional[SerialDevice]) -> None:
        self._serial_connection_device = device
        self._persistent_state.serial_connection_device = device
        self.broadcast()

    def set_usb_connection_device(self, device: Optional[USBDevice]) -> None:
        self._usb_connection_device = device
        self._persistent_state.usb_connection_device = device
        self.broadcast()

    def set_autoconnect_enabled(self, autoconnect_enabled: bool) -> None:
        self._persistent_state.autoconnect_enabled = autoconnect_enabled
        self.broadcast()

    def set_flow_control_enabled(self, flow_control_enabled: bool) -> None:
        self._persistent_state.flow_control_enabled = flow_control_enabled
        self.broadcast()

    def set_overridden_baudrate(self, overridden_baudrate: Optional[int]) -> None:
        self._persistent_state.overridden_baudrate = overridden_baudrate
        self.broadcast()

    def set_recording_enabled(self, recording_enabled: bool) -> None:
        self._persistent_state.recording_enabled = recording_enabled
        self.broadcast()

    def set_plugin_generation(self, new_generation: PluginGeneration) -> None:
        self._persistent_state.plugin_generation = new_generation
        self.broadcast()

    def _unload_current_plugin(self) -> None:
        log.debug("AppModel is unloading its current plugin")
        self.sig_load_plugin.emit(None)
        self._update_saveable_file(None)
        self.backend_plugin_state = None
        self.broadcast()

        Model.unload_plugin.rpc(self.put_task)

    def load_plugin(self, plugin: Optional[PluginSpec]) -> None:
        log.debug(f"AppModel is loading the plugin {plugin}")
        if plugin == self.plugin:
            return

        self._unload_current_plugin()

        if plugin is not None:
            Model.load_plugin.rpc(
                self.put_task,
                plugin_factory=plugin.create_backend_plugin,
                key=plugin.key,
            )
            BackendPlugin.load_from_cache.rpc(self.put_task)

        self.sig_load_plugin.emit(plugin)
        self.plugin = plugin
        self.broadcast()
        self.broadcast_backend_state()

    def set_plugin_preset(self, preset_id: Enum) -> None:
        BackendPlugin.set_preset.rpc(self.put_task, preset_id=preset_id.value)

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

        if findings.key is None:
            plugin = self.find_plugin("sparse_iq", self.plugin_generation)  # noqa: F841
        else:
            plugin = self.find_plugin(findings.key, self.plugin_generation)

            if plugin is None:
                log.debug(f"Could not find plugin '{findings.key}'")
                return

        self.load_plugin(plugin)
        BackendPlugin.load_from_file.rpc(self.put_task, path=path)

    def find_plugin(self, plugin_key: str, generation: PluginGeneration) -> Optional[PluginSpec]:
        return next(
            (
                plugin
                for plugin in self.plugins
                if plugin.key == plugin_key and plugin.generation == generation
            ),
            None,
        )

    @property
    def rss_version(self) -> Optional[str]:
        if self._a121_server_info is not None:
            return self._a121_server_info.rss_version

        return None

    @property
    def connected_sensors(self) -> list[int]:
        return self._a121_server_info.connected_sensors if self._a121_server_info else []

    def send_status_file_path(self, file_path: str, opened: bool) -> None:
        self.sig_status_file_path.emit(file_path, opened)

    def send_status_message(self, message: Optional[str]) -> None:
        self.sig_status_message.emit(message)

    def send_warning_message(self, message: Optional[str]) -> None:
        self.sig_status_message.emit(f'<p style="color: #FD5200;"><b>{message}</b></p>')
