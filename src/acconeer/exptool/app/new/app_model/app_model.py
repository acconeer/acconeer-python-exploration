from enum import Enum, auto

from PySide6.QtCore import QObject, QThread, Signal

from acconeer.exptool import a121
from acconeer.exptool.app.new.backend import Backend, Message


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()


class _BackendListeningThread(QThread):
    sig_received_from_backend = Signal(Message)

    def __init__(self, backend: Backend, parent: QObject) -> None:
        super().__init__(parent)
        self.backend = backend

    def run(self) -> None:
        while True:
            self.sig_received_from_backend.emit(self.backend.recv())


class AppModel(QObject):
    sig_notify = Signal(object)
    sig_error = Signal(Exception)

    def __init__(self, backend: Backend) -> None:
        super().__init__()
        self._backend = backend
        self._listener = _BackendListeningThread(self._backend, self)
        self._listener.sig_received_from_backend.connect(self._handle_backend_message)
        self.connection_state = ConnectionState.DISCONNECTED

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.quit()

    def broadcast(self) -> None:
        self.sig_notify.emit(self)

    def _handle_backend_message(self, message: Message) -> None:
        if message.status != "ok":
            self.sig_error.emit(message.exception)
            return

        if message.command_name == "connect_client":
            self.connection_state = ConnectionState.CONNECTED

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
