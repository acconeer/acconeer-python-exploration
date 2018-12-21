from abc import ABCMeta, abstractmethod


class BaseClient(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, **kwargs):
        self.squeeze = kwargs.get("squeeze", True)

        self._connected = False
        self._session_setup_done = False
        self._streaming_started = False

    def connect(self):
        if self._connected:
            raise ClientError("already connected")

        self._connect()
        self._connected = True

    def setup_session(self, config):
        if self._streaming_started:
            raise ClientError("can't setup session while streaming")

        if not self._connected:
            self.connect()

        session_info = self._setup_session(config)
        self._session_setup_done = True
        return session_info

    def start_streaming(self, config=None):
        if self._streaming_started:
            raise ClientError("already streaming")

        if config is None:
            ret = None
        else:
            ret = self.setup_session(config)

        if not self._session_setup_done:
            raise ClientError("session needs to be set up before starting stream")

        self._start_streaming()
        self._streaming_started = True
        return ret

    def get_next(self):
        if not self._streaming_started:
            raise ClientError("must be streaming to get next")

        return self._get_next()

    def stop_streaming(self):
        if not self._streaming_started:
            raise ClientError("not streaming")

        self._stop_streaming()
        self._streaming_started = False

    def disconnect(self):
        if not self._connected:
            raise ClientError("not connected")

        if self._streaming_started:
            self.stop_streaming()

        self._disconnect()
        self._connected = False

    @abstractmethod
    def _connect(self):
        pass

    @abstractmethod
    def _setup_session(self, config):
        pass

    @abstractmethod
    def _start_streaming(self):
        pass

    @abstractmethod
    def _get_next(self):
        pass

    @abstractmethod
    def _stop_streaming(self):
        pass

    @abstractmethod
    def _disconnect(self):
        pass


class ClientError(Exception):
    pass
