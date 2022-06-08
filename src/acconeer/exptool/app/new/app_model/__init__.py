from PySide6.QtCore import QObject

from acconeer.exptool.app.new.backend import Backend


class AppModel(QObject):
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
