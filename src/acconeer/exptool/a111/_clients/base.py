# Copyright (c) Acconeer AB, 2022
# All rights reserved

import abc
import logging

from packaging import version

from acconeer.exptool._structs import configbase
from acconeer.exptool.a111 import SDK_VERSION, _modes


log = logging.getLogger(__name__)


class BaseClient(abc.ABC):
    @abc.abstractmethod
    def __init__(self, **kwargs):
        self._squeeze = kwargs.pop("squeeze", True)

        if kwargs:
            a_key = next(iter(kwargs.keys()))
            raise TypeError("Got unexpected keyword argument ({})".format(a_key))

        self._connected = False
        self._session_setup_done = False
        self._streaming_started = False
        self.supported_modes = None

    def connect(self):
        """Initiates a connection with the device.

        :return: A dict containing information about the device, including SDK version
        :rtype: dict
        """
        if self._connected:
            raise ClientError("already connected")

        info = self._connect()
        self._connected = True

        if info is None:
            info = {}

        if not info.get("mock"):
            try:
                sensor = info.get("sensor")
                if sensor and sensor != "a111":
                    raise ClientError(f"Wrong sensor version, expected a111 but got {sensor}")
                log.info("reported version: {}".format(info["version_str"]))

                if info["strict_version"] < version.parse(SDK_VERSION):
                    log.warning("old server version - please upgrade server")
                elif info["strict_version"] > version.parse(SDK_VERSION):
                    log.warning("new server version - please upgrade client")
            except KeyError:
                log.warning("could not read software version (might be too old)")

        self.supported_modes = self._get_supported_modes()

        return info

    def setup_session(self, config, check_config=True):
        """
        Sets up a session with the given config.
        Will call ``connect()`` if not already connected.

        :param config: The configuration to use when setting up the session
        :type config: class:`acconeer.exptool.configs`
        :param check_config: If `True` the configuration is checked for errors,
                            defaults to `True`
        :type check_config: bool

        :return: A dict with metadata for the configured session
        :rtype: dict
        """
        if check_config:
            self._check_config(config)

        if self._streaming_started:
            raise ClientError("can't setup session while streaming")

        if not self._connected:
            self.connect()

        if check_config and config.mode not in self.supported_modes:
            raise ClientError("Unsupported mode")

        session_info = self._setup_session(config)
        self._session_setup_done = True
        return session_info

    def start_session(self, config=None, check_config=True):
        """
        Starts the session if previously set up with ``setup_session()``.
        If `config` is provided, ``setup_session()`` will be called.

        :param config: The configuration to use when setting up the session, defaults to `None`
        :type config: class:`acconeer.exptool.configs`, optional
        :param check_config: If `True` the configuration is checked for errors,
                            defaults to `True`
        :type check_config: bool

        :return: If `config` is provided, returns a dict with metadata for the configured session.
                Otherwise, returns `None`
        :rtype: dict or None
        """
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
        """
        Retrieves the next result. Will block until the result is received.

        :return: A tuple with the result info and data.
                The data shape and type differs between services.

                | **Power Bins:**
                | Shape: (number of sensors, bin count)
                | Type: float64

                | **Envelope:**
                | Shape: (number of sensors, data length)
                | Type: float64

                | **IQ:**
                | Shape: (number of sensors, data length)
                | Type: complex128

                | **Sparse:**
                | Shape: (number of sensors, number of sweeps, number of dephts)
                | Type: float64

                `Number of sensors`, `bin count` and `number of sweeps` can be explicitly set.
                `Data length` and `number of dephts` depend on multiple configuration settings.

                The client takes a parameter ``squeeze``, if set to `True` the first
                dimension (`number of sensors`) is removed when using a single sensor.
                As default ``squeeze`` is  `True`.

        :rtype: tuple[union[list, dict], np.ndarray]
        """
        if not self._streaming_started:
            raise ClientError("must be streaming to get next")

        return self._get_next()

    def stop_session(self):
        """
        Stops the session. All buffered/waiting data is thrown away.
        This function will block until the server has confirmed that the session has ended.
        """
        if not self._streaming_started:
            raise ClientError("not streaming")

        self._stop_session()
        self._streaming_started = False

    def disconnect(self):
        """
        Disconnects the client. ``disconnect()`` will call ``stop_session()``
        if a session is started.
        """
        if not self._connected:
            raise ClientError("not connected")

        if self._streaming_started:
            self.stop_session()

        self._disconnect()
        self._connected = False
        self.supported_modes = None

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

    @property
    @abc.abstractmethod
    def description(self):
        pass

    def _get_supported_modes(self):
        return set(_modes.Mode)

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

    @property
    def squeeze(self):
        return self._squeeze

    @squeeze.setter
    def squeeze(self, squeeze):
        self._squeeze = squeeze


class ClientError(Exception):
    pass


class IllegalConfigError(ClientError):
    pass


class SessionSetupError(ClientError):
    pass


def decode_version_str(version_str: str) -> dict:
    if version_str.startswith("a111-"):
        version_str = version_str[5:]

    if version_str.startswith("v"):
        version_str = version_str[1:]

    if "-" in version_str:
        strict_version = version.parse(version_str.split("-")[0])
    else:
        strict_version = version.parse(version_str)

    return {
        "version_str": version_str,
        "strict_version": strict_version,
    }
