# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
import typing as t

from acconeer.exptool._core.communication import client
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.recording import Recorder


class Client(
    client.Client[
        SessionConfig,  # Config type
        t.List[t.Dict[int, Metadata]],  # Metadata type
        t.List[t.Dict[int, Result]],  # Result type
        ServerInfo,  # Server info type
        Recorder,  # Recorder type
    ],
    register=False,
):
    @abc.abstractmethod
    def setup_session(  # type: ignore[override]
        self,
        config: t.Union[SensorConfig, SessionConfig],
        calibrations: t.Optional[dict[int, SensorCalibration]] = None,
    ) -> t.Union[Metadata, list[dict[int, Metadata]]]:
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
    def get_next(self) -> t.Union[Result, list[dict[int, Result]]]:  # type: ignore[override]
        """Gets results from the server.

        :returns:
            A ``Result`` if the setup ``SessionConfig.extended is False``,
            ``list[dict[int, Result]]`` otherwise.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
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

    def __exit__(self, *_: t.Any) -> None:
        self.close()
