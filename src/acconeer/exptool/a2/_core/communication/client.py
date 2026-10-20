# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import abc
import typing as t
from enum import Enum, auto

import typing_extensions as te

from acconeer.exptool._core.communication import client
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a2._core.entities import (
    GroupResult,
    Metadata,
    Result,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a2._core.recording import H5Recorder


class Client(
    client.Client[SessionConfig, Metadata, GroupResult, ServerInfo, H5Recorder],
    register=False,
):
    class ResultFormat(Enum):
        """Decide the format of the data returned by :class:`Client.get_next`"""

        AUTO = auto()
        SOLE = auto()
        FULL = auto()

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
        generation: t.Optional[str] = "a2",
    ) -> te.Self:
        return super().open(
            ip_address,
            tcp_port,
            serial_port,
            usb_device,
            mock,
            override_baudrate,
            flow_control,
            generation="a2",
        )

    def __init__(self, client_info: ClientInfo, enable_diagnosticts: bool = False) -> None:
        super().__init__(client_info)

        self._enable_diagnostics = enable_diagnosticts
        self._closed = False
        self._crashing = False
        self._config: t.Optional[SessionConfig] = None
        self._calibration_provided: bool = False

    @abc.abstractmethod
    def setup_session(
        self, config: SessionConfig, calibration: t.Optional[str] = None
    ) -> Metadata:
        """Sets up the session specified by ``config``

        A session is typically setup by performing radar calibration on the Exploration Server.

        Sensor calibrations may be reused by reading it from :py:attr:`Metadata.sensor_calibration`
        passing it to the ``calibration`` parameter.
        """
        pass

    @property
    def calibration(self) -> str:
        """
        Returns the calibration string if calibration was performed in setup_session(),

        :raises:
            ``ClientError`` if ``Client`` did not provide calibration.
        """
        self._assert_session_setup()
        assert self._metadata is not None

        if self._metadata.sensor_calibration is None:
            msg = "Server did not provide calibration"
            raise client.ClientError(msg)

        return self._metadata.sensor_calibration

    @property
    def calibration_provided(self) -> bool:
        """
        Returns whether a calibration was provided in setup_session.
        """
        return self._calibration_provided

    @te.overload  # type: ignore[override]
    def get_next(self) -> t.Union[GroupResult, Result]: ...

    @te.overload
    def get_next(
        self, *, format: te.Literal[ResultFormat.AUTO]
    ) -> t.Union[GroupResult, Result]: ...

    @te.overload
    def get_next(self, *, format: te.Literal[ResultFormat.FULL]) -> GroupResult: ...

    @te.overload
    def get_next(self, *, format: te.Literal[ResultFormat.SOLE]) -> Result: ...

    def get_next(
        self, *, format: ResultFormat = ResultFormat.AUTO
    ) -> t.Union[GroupResult, Result]:
        """Gets results from the server.

        :param format:
            Decides the format of the returned result.

            - AUTO
                return a :class:`Result` if the setup :class:`SessionConfig`
                has exactly one :class:`SensorConfig`, :class:`GroupResult` otherwise.

            - SOLE
                Always return a :class:`Result`, raises an error if the setup
                :class:`SessionConfig` has more than one :class:`SensorConfig`.

            - FULL
                Always return :class:`GroupResult`
        :returns:
            See ``format``.
        :raises:
            ``ClientError`` if the session is not started or
            a sole :class:`Result` could not be received.
        """
        self._assert_session_started()
        assert self._config is not None

        group_result = self._get_next_group_result()

        self._recorder_sample(group_result)

        if format is self.ResultFormat.FULL:
            return group_result
        elif format is self.ResultFormat.SOLE:
            try:
                return group_result.result
            except AttributeError as ae:
                raise client.ClientError(*ae.args)
        elif format is self.ResultFormat.AUTO:
            if len(self._config.sensor_configs) == 1:
                return group_result.result
            else:
                return group_result
        else:
            te.assert_never(format)

    @abc.abstractmethod
    def _get_next_group_result(self) -> GroupResult:
        pass

    def stop_session(self) -> None:
        """Stops an on-going session

        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        self._session_is_started = False
        self._recorder_stop_session()

    @property
    def connected(self) -> bool:
        """Whether this Client is connected."""
        return self.server_info is not None

    @property
    @abc.abstractmethod
    def server_info(self) -> ServerInfo:
        """The :class:`ServerInfo`"""

    @property
    def tick_period(self) -> int:
        """The theoretical number of ticks between results"""
        self._assert_session_setup()
        assert self._metadata is not None

        return self._metadata.tick_period

    @property
    def session_config(self) -> SessionConfig:
        """The :class:`SessionConfig` this client is setup with"""
        self._assert_session_setup()
        assert self._config is not None

        return self._config

    def _recorder_sample(self, result: GroupResult) -> None:
        if self._recorder is None:
            return

        self._recorder._sample(result)

    def _recorder_start(self, recorder: H5Recorder) -> None:
        if recorder is None:
            return

        recorder._start(
            client_info=self.client_info,
            server_info=self.server_info,
        )

    def _recorder_start_session(self) -> None:
        if self._recorder is None:
            return

        assert self._config is not None
        assert self._metadata is not None

        self._recorder._start_session(
            config=self._config,
            metadata=self._metadata,
        )

    def _recorder_stop_session(self) -> None:
        if self._recorder is None:
            return

        self._recorder._stop_session()
