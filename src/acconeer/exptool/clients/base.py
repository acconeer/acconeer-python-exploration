import abc
import logging
from distutils.version import StrictVersion

from acconeer.exptool import SDK_VERSION


log = logging.getLogger(__name__)


class BaseClient(abc.ABC):
    @abc.abstractmethod
    def __init__(self, **kwargs):
        self.squeeze = kwargs.get("squeeze", True)

        self._connected = False
        self._session_setup_done = False
        self._streaming_started = False

    def connect(self):
        if self._connected:
            raise ClientError("already connected")

        info = self._connect()
        self._connected = True

        if info is None:
            info = {}

        try:
            log.info("reported version: {}".format(info["version_str"]))

            if info["strict_version"] < StrictVersion(SDK_VERSION):
                log.warning("old server version - please upgrade server")
            elif info["strict_version"] > StrictVersion(SDK_VERSION):
                log.warning("new server version - please upgrade client")
        except KeyError:
            log.warning("could not read software version (might be too old)")

        return info

    def setup_session(self, config):
        if self._streaming_started:
            raise ClientError("can't setup session while streaming")

        if not self._connected:
            self.connect()

        session_info = self._setup_session(config)
        self._session_setup_done = True

        try:
            start_ok = abs(config.range_start - session_info["range_start_m"]) < 0.01
            len_ok = abs(config.range_length - session_info["range_length_m"]) < 0.01
        except (AttributeError, KeyError, TypeError):
            pass
        else:
            if not start_ok or not len_ok:
                log.warning("actual measured range differs from the requested")

        return session_info

    def start_session(self, config=None):
        if self._streaming_started:
            raise ClientError("already streaming")

        if config is None:
            ret = None
        else:
            ret = self.setup_session(config)

        if not self._session_setup_done:
            raise ClientError("session needs to be set up before starting stream")

        self._start_session()
        self._streaming_started = True
        return ret

    def get_next(self):
        if not self._streaming_started:
            raise ClientError("must be streaming to get next")

        return self._get_next()

    def stop_session(self):
        if not self._streaming_started:
            raise ClientError("not streaming")

        self._stop_session()
        self._streaming_started = False

    def disconnect(self):
        if not self._connected:
            raise ClientError("not connected")

        if self._streaming_started:
            self.stop_session()

        self._disconnect()
        self._connected = False

    @abc.abstractmethod
    def _connect(self):
        pass

    @abc.abstractmethod
    def _setup_session(self, config):
        pass

    @abc.abstractmethod
    def _start_session(self):
        pass

    @abc.abstractmethod
    def _get_next(self):
        pass

    @abc.abstractmethod
    def _stop_session(self):
        pass

    @abc.abstractmethod
    def _disconnect(self):
        pass


class ClientError(Exception):
    pass


class SessionSetupError(ClientError):
    pass


def decode_version_str(version: str):
    if "-" in version:
        strict_version = StrictVersion(version.split("-")[0])
    else:
        strict_version = StrictVersion(version)

    return {
        "version_str": version,
        "strict_version": strict_version,
    }
