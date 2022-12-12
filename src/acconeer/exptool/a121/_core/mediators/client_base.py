# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Optional, Union

from typing_extensions import Protocol

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._rate_calc import _RateStats

from .recorder import Recorder


class ClientError(Exception):
    pass


class ClientBase(Protocol):
    def connect(self) -> None:
        """Connects to the specified host.

        :raises: Exception if the host cannot be connected to.
        :raises: ClientError if server has wrong sensor generation (e.g. "a111")
        """
        ...

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        """Sets up the session specified by ``config``.

        If the Client is not already connected, it will connect before setting up the session.

        :param config: The session to set up.
        :param calibrations: An optional dict with :class:`SensorCalibration` for the session.
        :raises:
            ``ValueError`` if the config is invalid.

        :returns:
            ``Metadata`` if ``config.extended is False``,
            ``list[dict[int, Metadata]]`` otherwise.
        """
        ...

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        """Starts the already set up session.

        After this call, the server starts streaming data to the client.

        :param recorder:
            An optional ``Recorder``, which samples every ``get_next()``
        :raises: ``ClientError`` if ``Client``'s  session is not set up.
        """
        ...

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        """Gets results from the server.

        :returns:
            A ``Result`` if the setup ``SessionConfig.extended is False``,
            ``list[dict[int, Result]]`` otherwise.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        ...

    def stop_session(self) -> Any:
        """Stops an on-going session

        :returns:
            The return value of the passed ``Recorder.stop()`` passed in ``start_session``.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        ...

    def disconnect(self) -> None:
        """Disconnects the client from the host."""
        ...

    @property
    def connected(self) -> bool:
        """Whether this Client is connected."""
        ...

    @property
    def session_is_setup(self) -> bool:
        """Whether this Client has a session set up."""
        ...

    @property
    def session_is_started(self) -> bool:
        """Whether this Client's session is started."""
        ...

    @property
    def server_info(self) -> ServerInfo:
        """The ``ServerInfo``."""
        ...

    @property
    def client_info(self) -> ClientInfo:
        """The ``ClientInfo``."""
        ...

    @property
    def session_config(self) -> SessionConfig:
        """The :class:`SessionConfig` for the current session"""
        ...

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        """The extended :class:`Metadata` for the current session"""
        ...

    @property
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

    @property
    def _rate_stats(self) -> _RateStats:
        """Returns the data rate statistict from the client"""
        ...
