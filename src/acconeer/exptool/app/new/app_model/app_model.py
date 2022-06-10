import logging
import queue
from enum import Enum, auto

from PySide6.QtCore import QDeadlineTimer, QObject, QThread, Signal

from acconeer.exptool import a121
from acconeer.exptool.app.new.backend import Backend, Message

from .core_store import CoreStore


log = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()


class ConnectionInterface(Enum):
    SERIAL = auto()
    SOCKET = auto()


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
    sig_error = Signal(Exception)

    def __init__(self, backend: Backend) -> None:
        super().__init__()
        self._backend = backend
        self._listener = _BackendListeningThread(self._backend, self)
        self._listener.sig_received_from_backend.connect(self._handle_backend_message)
        self._core_store = CoreStore()
        self.connection_state = ConnectionState.DISCONNECTED
        self.connection_interface = ConnectionInterface.SERIAL

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.requestInterruption()
        status = self._listener.wait(QDeadlineTimer(500))

        if not status:
            log.debug("Backend listening thread did not stop when requested, terminating...")
            self._listener.terminate()

    def broadcast(self) -> None:
        self.sig_notify.emit(self)

    def _handle_backend_message(self, message: Message) -> None:
        log.debug(f"{self.__class__.__name__} got from server: {message}")
        if message.status == "error":
            self.sig_error.emit(message.exception)

        if message.command_name == "connect_client":
            if message.status == "ok":
                self.connection_state = ConnectionState.CONNECTED
            else:
                self.connection_state = ConnectionState.DISCONNECTED
        elif message.command_name == "disconnect_client":
            if message.status == "ok":
                self.connection_state = ConnectionState.DISCONNECTED
            else:
                self.connection_state = ConnectionState.CONNECTED
        elif message.command_name == "server_info":
            self._core_store.server_info = message.data

        self.broadcast()

    def connect_client(self, client_info: a121.ClientInfo) -> None:
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
