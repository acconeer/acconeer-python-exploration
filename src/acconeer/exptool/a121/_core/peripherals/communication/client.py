# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
from typing import Any, List, Optional, Type, Union

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.mediators import Recorder

from .communication_protocol import CommunicationProtocol


class ClientError(Exception):
    pass


class ClientCreationError(Exception):
    pass


class ClientABCWithGoodError(abc.ABC):
    def __new__(cls, *args: Any, **kwargs: Any) -> ClientABCWithGoodError:
        try:
            return super().__new__(cls)  # , *args, **kwargs)
        except TypeError as te:  # te here is the "Can't instantiate ..."-error
            raise ClientCreationError("Client cannot be instantiated, use Client.open()") from te


class Client(ClientABCWithGoodError):

    __registry: List[Type[Client]] = []

    @classmethod
    def open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ) -> Client:
        """
        Open a new client
        """
        if len([e for e in [ip_address, serial_port, usb_device, mock] if e is not None]) > 1:
            raise ValueError("Only one connection can be selected")

        client = None
        for subclass in cls.__registry:
            try:
                client = subclass.open(
                    ip_address,
                    tcp_port,
                    serial_port,
                    usb_device,
                    mock,
                    override_baudrate,
                    _override_protocol,
                )
            except ClientCreationError:
                pass

        if client is not None:
            client._open()
            return client

        # This should not happen since the current implementation
        # only has two clients which are mutual exclusive.
        # * The mock client (mock is not None)
        # * The exploration client (mock is None)
        raise ClientCreationError("No client could be created")

    @classmethod
    def _register(cls, subclass: Type[Client]) -> Type[Client]:
        """Registers a subclass"""
        if not issubclass(subclass, cls):
            raise TypeError(f"{subclass.__name__!r} needs to be a subclass of {cls.__name__}.")
        cls.__registry.append(subclass)
        return subclass

    @abc.abstractmethod
    def _open(self) -> None:
        """Connects to client, called from open"""
        ...

    @abc.abstractmethod
    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        """Sets up the session specified by ``config``.

        :param config: The session to set up.
        :param calibrations: An optional dict with :class:`SensorCalibration` for the session.
        :raises:
            ``ValueError`` if the config is invalid.

        :returns:
            ``Metadata`` if ``config.extended is False``,
            ``list[dict[int, Metadata]]`` otherwise.
        """
        ...

    @abc.abstractmethod
    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        """Starts the already set up session.

        After this call, the server starts streaming data to the client.

        :param recorder:
            An optional ``Recorder``, which samples every ``get_next()``
        :raises: ``ClientError`` if ``Client``'s  session is not set up.
        """
        ...

    @abc.abstractmethod
    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        """Gets results from the server.

        :returns:
            A ``Result`` if the setup ``SessionConfig.extended is False``,
            ``list[dict[int, Result]]`` otherwise.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        ...

    @abc.abstractmethod
    def stop_session(self) -> Any:
        """Stops an on-going session

        :returns:
            The return value of the passed ``Recorder.stop()`` passed in ``start_session``.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        ...

    @abc.abstractmethod
    def close(self) -> None:
        """Disconnects the client from the host."""
        ...

    @property
    @abc.abstractmethod
    def connected(self) -> bool:
        """Whether this Client is connected."""
        ...

    @property
    @abc.abstractmethod
    def session_is_setup(self) -> bool:
        """Whether this Client has a session set up."""
        ...

    @property
    @abc.abstractmethod
    def session_is_started(self) -> bool:
        """Whether this Client's session is started."""
        ...

    @property
    @abc.abstractmethod
    def server_info(self) -> ServerInfo:
        """The ``ServerInfo``."""
        ...

    @property
    @abc.abstractmethod
    def client_info(self) -> ClientInfo:
        """The ``ClientInfo``."""
        ...

    @property
    @abc.abstractmethod
    def session_config(self) -> SessionConfig:
        """The :class:`SessionConfig` for the current session"""
        ...

    @property
    @abc.abstractmethod
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        """The extended :class:`Metadata` for the current session"""
        ...

    @property
    @abc.abstractmethod
    def calibrations(self) -> dict[int, SensorCalibration]:
        """
        Returns a dict with a :class:`SensorCalibration` per used
        sensor for the current session:

        For example, if session_setup was called with

        .. code-block:: python

            client.setup_session(
                SessionConfig({1: SensorConfig(), 3: SensorConfig()}),
            )

        this attribute will return {1: SensorCalibration(...), 3: SensorCalibration(...)}
        """
        ...

    @property
    @abc.abstractmethod
    def calibrations_provided(self) -> dict[int, bool]:
        """
        Returns whether a calibration was provided for each sensor in
        setup_session. For example, if setup_session was called with

        .. code-block:: python

            client.setup_session(
                SessionConfig({1: SensorConfig(), 2: SensorConfig()}),
                calibrations={2: SensorCalibration(...)},
            )

        this attribute will return ``{1: False, 2: True}``
        """
        ...

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
