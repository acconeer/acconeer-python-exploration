# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import time
import warnings
from typing import Any, Iterator, Optional, Union

import acconeer.exptool.a121._core.utils as core_utils
from acconeer.exptool.a121 import (
    Client,
    ClientError,
    ClientInfo,
    Metadata,
    Record,
    Recorder,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)


class _StopReplay(Exception):
    pass


class _ReplayingClient(Client):
    def __init__(self, record: Record, *, cycled_session_idx: Optional[int] = None):
        """
        :param record: The Record to replay from
        :param cycled_session_idx:
            If specified, cycle (reuse as next session) the session
            specified by 'cycled_session_idx'.
        """
        self._record = record
        self._is_started: bool = False
        self._result_iterator: Iterator[list[dict[int, Result]]] = iter([])
        self._origin_time: Optional[float] = None
        self._session_idx = 0
        self._cycled_session_idx = cycled_session_idx

    @property
    def _actual_session_idx(self) -> int:
        if self._cycled_session_idx is not None:
            return self._cycled_session_idx
        else:
            return self._session_idx

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

    def _open(self) -> None:
        pass

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        if config != self.session_config:
            raise ValueError

        if self.session_config.extended:
            return self.extended_metadata
        else:
            return core_utils.unextend(self.extended_metadata)

    def start_session(self) -> None:
        self._result_iterator = self._record.session(self._actual_session_idx).extended_results
        self._is_started = True
        self._origin_time = None

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        if not self.session_is_setup:
            raise ClientError("Session is not set up.")

        assert self._result_iterator is not None

        try:
            result = next(self._result_iterator)
        except StopIteration:
            raise _StopReplay

        some_result = next(core_utils.iterate_extended_structure_values(result))

        now = time.monotonic() - some_result.tick_time

        if self._origin_time is None:
            self._origin_time = now

        delta = now - self._origin_time

        if delta < 0:
            time.sleep(-delta)

        if self.session_config.extended:
            return result
        else:
            return core_utils.unextend(result)

    def stop_session(self) -> Any:
        try:
            _ = next(self._result_iterator)
        except StopIteration:
            pass
        else:
            warnings.warn(f"Results of session {self._actual_session_idx} were not exhausted.")

        self._session_idx += 1
        self._is_started = False

    def attach_recorder(self, recorder: Recorder) -> None:
        pass

    def detach_recorder(self) -> Optional[Recorder]:
        return None

    def close(self) -> None:
        pass

    @property
    def connected(self) -> bool:
        return True

    @property
    def session_is_setup(self) -> bool:
        return True

    @property
    def session_is_started(self) -> bool:
        return self._is_started

    @property
    def server_info(self) -> ServerInfo:
        return self._record.server_info

    @property
    def client_info(self) -> ClientInfo:
        return self._record.client_info

    @property
    def session_config(self) -> SessionConfig:
        return self._record.session(self._actual_session_idx).session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._record.session(self._actual_session_idx).extended_metadata

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        return self._record.session(self._actual_session_idx).calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        return self._record.session(self._actual_session_idx).calibrations_provided
