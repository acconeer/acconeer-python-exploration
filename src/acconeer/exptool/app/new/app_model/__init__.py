from acconeer.exptool.app.new.backend import Backend


class AppModel:
    def __init__(self, backend: Backend) -> None:
        self._backend = backend

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
