import abc
import logging
from distutils.version import StrictVersion

from acconeer.exptool import SDK_VERSION
from acconeer.exptool.structs import configbase


log = logging.getLogger(__name__)


class BaseClient(abc.ABC):
    @abc.abstractmethod
    def __init__(self, **kwargs):
        self.squeeze = kwargs.pop("squeeze", True)

        if kwargs:
            a_key = next(iter(kwargs.keys()))
            raise TypeError("Got unexpected keyword argument ({})".format(a_key))

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

        if not info.get("mock"):
            try:
                log.info("reported version: {}".format(info["version_str"]))

                if info["strict_version"] < StrictVersion(SDK_VERSION):
                    log.warning("old server version - please upgrade server")
                elif info["strict_version"] > StrictVersion(SDK_VERSION):
                    log.warning("new server version - please upgrade client")
            except KeyError:
                log.warning("could not read software version (might be too old)")

        return info

    def setup_session(self, config, check_config=True):
        if check_config:
            self._check_config(config)

        if self._streaming_started:
            raise ClientError("can't setup session while streaming")

        if not self._connected:
            self.connect()

        session_info = self._setup_session(config)
        self._session_setup_done = True
        return session_info

    def start_session(self, config=None, check_config=True):
        if self._streaming_started:
            raise ClientError("already streaming")

        if config is None:
            ret = None
        else:
            ret = self.setup_session(config, check_config=check_config)

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

    def _check_config(self, config):
        try:
            alerts = config.check()
        except AttributeError:
            return

        try:
            error_alert = next(a for a in alerts if a.severity == configbase.Severity.ERROR)
        except StopIteration:
            return

        msg = "error in config: {}: {}".format(error_alert.param, error_alert.msg)
        raise IllegalConfigError(msg)

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


class IllegalConfigError(ClientError):
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
