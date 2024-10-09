# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import abc
import typing as t

import typing_extensions as te

from acconeer.exptool._core.communication import Client as BaseClient
from acconeer.exptool._core.communication import ClientCreationError, ClientError
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.recording import Recorder
from acconeer.exptool.a121._core.utils import unextend


class Client(
    BaseClient[
        SessionConfig,  # Config type
        t.List[t.Dict[int, Metadata]],  # Metadata type
        t.List[t.Dict[int, Result]],  # Result type
        ServerInfo,  # Server info type
        Recorder,  # Recorder type
    ],
    register=False,
):
    @classmethod
    def open(
        cls,
        ip_address: t.Optional[str] = None,
        tcp_port: t.Optional[int] = None,
        serial_port: t.Optional[str] = None,
        usb_device: t.Optional[t.Union[str, bool]] = None,
        mock: t.Optional[bool] = None,
        override_baudrate: t.Optional[int] = None,
        flow_control: bool = True,
        generation: t.Optional[str] = "a121",
    ) -> te.Self:
        if generation != "a121":
            raise ClientCreationError

        return super().open(
            ip_address,
            tcp_port,
            serial_port,
            usb_device,
            mock,
            override_baudrate,
            flow_control,
            generation="a121",
        )

    def __init__(self, client_info: ClientInfo) -> None:
        super().__init__(client_info)
        self._sensor_calibrations: t.Optional[dict[int, SensorCalibration]] = None
        self._calibrations_provided: dict[int, bool] = {}
        self._session_config: t.Optional[SessionConfig] = None

    def _return_results(
        self, extended_results: list[dict[int, Result]]
    ) -> t.Union[Result, list[dict[int, Result]]]:
        if self.session_config.extended:
            return extended_results
        else:
            return unextend(extended_results)

    @property
    def session_config(self) -> SessionConfig:
        """The :class:`SessionConfig` for the current session"""
        self._assert_session_setup()
        assert self._session_config is not None  # Should never happen if session is setup
        return self._session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        """The extended :class:`Metadata` for the current session"""
        self._assert_session_setup()
        assert self._metadata is not None  # Should never happen if session is setup
        return self._metadata

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
        self._assert_session_setup()

        if not self._sensor_calibrations:
            msg = "Server did not provide calibration"
            raise ClientError(msg)

        return self._sensor_calibrations

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
        return self._calibrations_provided

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

    def _recorder_start(self, recorder: Recorder) -> None:
        recorder._start(
            client_info=self.client_info,
            server_info=self.server_info,
        )

    def _recorder_start_session(self) -> None:
        if self._recorder is not None:
            calibrations_provided: t.Optional[dict[int, bool]] = self.calibrations_provided
            try:
                calibrations = self.calibrations
            except ClientError:
                calibrations = None
                calibrations_provided = None

            self._recorder._start_session(
                config=self.session_config,
                metadata=self.extended_metadata,
                calibrations=calibrations,
                calibrations_provided=calibrations_provided,
            )

    def _recorder_sample(self, result: list[dict[int, Result]]) -> None:
        if self._recorder is not None:
            self._recorder._sample(result)

    def _recorder_stop_session(self) -> None:
        if self._recorder is not None:
            self._recorder._stop_session()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: t.Any) -> None:
        self.close()
