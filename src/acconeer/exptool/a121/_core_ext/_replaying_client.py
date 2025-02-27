# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import itertools
import time
import warnings
from typing import Any, Iterator, Optional, Union

import acconeer.exptool.a121._core.utils as core_utils
from acconeer.exptool._core import ClientInfo
from acconeer.exptool._core.communication.client import ClientError
from acconeer.exptool.a121 import (
    Client,
    Metadata,
    Record,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)


class _StopReplay(Exception):
    pass


class ReplaySessionsExhaustedError(Exception):
    pass


class _ReplayingClient(Client, register=False):
    def __init__(
        self,
        record: Record,
        *,
        cycled_session_idx: Optional[int] = None,
        realtime_replay: bool = True,
    ):
        """
        :param record: The Record to replay from
        :param cycled_session_idx:
            If specified, cycle (reuse as next session) the session
            specified by 'cycled_session_idx'.
        :param realtime_replay: If True, replays the data at the rate of recording
        """
        super().__init__(record.client_info)
        self._record = record
        self._is_started: bool = False
        self._result_iterator: Iterator[list[dict[int, Result]]] = iter([])
        self._origin_time: Optional[float] = None
        self._realtime_replay = realtime_replay
        self._session_idx: Optional[int] = None
        self._session_idx_iter: Union[Iterator[int], itertools.repeat[int]]
        if cycled_session_idx is not None:
            self._session_idx_iter = itertools.repeat(cycled_session_idx)
        else:
            self._session_idx_iter = iter(range(record.num_sessions))

    @property
    def _actual_session_idx(self) -> int:
        if self._session_idx is not None:
            return self._session_idx
        else:
            msg = "Session is not set up."
            raise ClientError(msg)

    def _assert_connected(self) -> None:
        if not self.connected:
            msg = "Client is not connected."
            raise ClientError(msg)

    def _assert_session_setup(self) -> None:
        self._assert_connected()
        if not self.session_is_setup:
            msg = "Session is not set up."
            raise ClientError(msg)

    def _assert_session_started(self) -> None:
        self._assert_session_setup()
        if not self.session_is_started:
            msg = "Session is not started."
            raise ClientError(msg)

    def _open(self) -> None:
        pass

    def setup_session(  # type: ignore[override]
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        try:
            new_session_idx = next(self._session_idx_iter)
        except StopIteration:
            raise ReplaySessionsExhaustedError
        else:
            self._session_idx = new_session_idx

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

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:  # type: ignore[override]
        if not self.session_is_setup:
            msg = "Session is not set up."
            raise ClientError(msg)

        assert self._result_iterator is not None

        try:
            result = next(self._result_iterator)
        except StopIteration:
            raise _StopReplay

        some_result = next(core_utils.iterate_extended_structure_values(result))

        if self._realtime_replay:
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

        self._is_started = False

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
