# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Optional, Union

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorCalibration,
    SessionConfig,
)
from acconeer.exptool.a121._core.mediators import Recorder
from acconeer.exptool.a121._core.utils import unextend

from .client import Client, ClientError


class CommonClient(Client):
    _client_info: ClientInfo
    _calibrations_provided: dict[int, bool]
    _metadata: Optional[list[dict[int, Metadata]]]
    _recorder: Optional[Recorder]
    _sensor_calibrations: Optional[dict[int, SensorCalibration]]
    _session_config: Optional[SessionConfig]
    _session_is_started: bool

    def _assert_connected(self) -> None:
        if not self.connected:
            raise ClientError("Client is not connected.")

    def _assert_session_setup(self) -> None:
        self._assert_connected()
        if not self.session_is_setup:
            raise ClientError("Session is not set up.")

    def _assert_session_started(self) -> None:
        self._assert_session_setup()
        if not self.session_is_started:
            raise ClientError("Session is not started.")

    def __init__(self, client_info: ClientInfo) -> None:
        self._client_info = client_info
        self._calibrations_provided = {}
        self._metadata = None
        self._recorder = None
        self._sensor_calibrations = None
        self._session_is_started = False
        self._session_config = None

    def attach_recorder(self, recorder: Recorder) -> None:
        if self.session_is_started:
            raise ClientError("Cannot attach a recorder when session is started.")

        if not self.connected:
            raise ClientError("Cannot attach a recorder to a closed client")

        if self._recorder is not None:
            raise ClientError(
                "Client already has a recorder attached. "
                + "Try detaching the current recorder before attaching a new recorder."
            )

        self._recorder = recorder
        self._recorder._start(
            client_info=self.client_info,
            server_info=self.server_info,
        )

    def detach_recorder(self) -> Optional[Recorder]:
        if self.session_is_started:
            raise ClientError("Cannot detach a recorder when session is started.")

        if not self.connected:
            raise ClientError("Cannot detach a recorder from a closed client")

        if self._recorder is None:
            return None
        else:
            previously_attached_recorder = self._recorder
            self._recorder = None
            return previously_attached_recorder

    def _recorder_start_session(self) -> None:
        if self._recorder is not None:
            calibrations_provided: Optional[dict[int, bool]] = self.calibrations_provided
            try:
                calibrations = self.calibrations
            except ClientError:
                calibrations = None
                calibrations_provided = None

            self._recorder._start_session(
                session_config=self.session_config,
                extended_metadata=self.extended_metadata,
                calibrations=calibrations,
                calibrations_provided=calibrations_provided,
            )

    def _recorder_stop_session(self) -> None:
        if self._recorder is not None:
            self._recorder._stop_session()

    def _recorder_sample(self, extended_results: list[dict[int, Result]]) -> None:
        if self._recorder is not None:
            self._recorder._sample(extended_results)

    def _return_results(
        self, extended_results: list[dict[int, Result]]
    ) -> Union[Result, list[dict[int, Result]]]:
        if self.session_config.extended:
            return extended_results
        else:
            return unextend(extended_results)

    @property
    def session_is_setup(self) -> bool:
        return self._metadata is not None

    @property
    def session_is_started(self) -> bool:
        return self._session_is_started

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info

    @property
    def session_config(self) -> SessionConfig:
        self._assert_session_setup()
        assert self._session_config is not None  # Should never happen if session is setup
        return self._session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        self._assert_session_setup()
        assert self._metadata is not None  # Should never happen if session is setup
        return self._metadata

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        self._assert_session_setup()

        if not self._sensor_calibrations:
            raise ClientError("Server did not provide calibration")

        return self._sensor_calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        return self._calibrations_provided
