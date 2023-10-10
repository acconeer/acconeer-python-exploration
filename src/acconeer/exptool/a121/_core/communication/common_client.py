# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Optional, Union

from acconeer.exptool._core.communication.client import ClientError
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    SessionConfig,
)
from acconeer.exptool.a121._core.recording import Recorder
from acconeer.exptool.a121._core.utils import unextend

from .client import Client


class CommonClient(Client, register=False):
    _metadata: Optional[list[dict[int, Metadata]]]

    def __init__(self, client_info: ClientInfo) -> None:
        super().__init__(client_info)
        self._sensor_calibrations: Optional[dict[int, SensorCalibration]] = None
        self._calibrations_provided: dict[int, bool] = {}
        self._session_config: Optional[SessionConfig] = None

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
                config=self.session_config,
                metadata=self.extended_metadata,
                calibrations=calibrations,
                calibrations_provided=calibrations_provided,
            )

    def _recorder_stop_session(self) -> None:
        if self._recorder is not None:
            self._recorder._stop_session()

    def _recorder_sample(self, result: list[dict[int, Result]]) -> None:
        if self._recorder is not None:
            self._recorder._sample(result)

    def _return_results(
        self, extended_results: list[dict[int, Result]]
    ) -> Union[Result, list[dict[int, Result]]]:
        if self.session_config.extended:
            return extended_results
        else:
            return unextend(extended_results)

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
