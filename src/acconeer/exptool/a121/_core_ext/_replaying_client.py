# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import time
from typing import Any, Dict, Iterator, List, Optional, Union, cast

from acconeer.exptool.a121 import (
    ClientBase,
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
from acconeer.exptool.a121._rate_calc import _RateCalculator, _RateStats


class _StopReplay(Exception):
    pass


class _ReplayingClient(ClientBase):
    _rate_stats_calc: Optional[_RateCalculator]

    def __init__(self, record: Record):
        self._record = record
        self._is_started: bool = False
        self._result_iterator: Optional[
            Union[Iterator[Result], Iterator[list[dict[int, Result]]]]
        ] = None
        self._origin_time: Optional[float] = None
        self._rate_stats_calc = None

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

    def connect(self) -> None:
        pass

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if not self.connected:
            self.connect()

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        if config != self._record.session_config:
            raise ValueError

        if self.session_config.extended:
            return self._record.extended_metadata
        else:
            return self._record.metadata

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        if recorder is not None:
            raise ValueError(f"{type(self).__name__} can not record")

        if self.session_config.extended:
            self._result_iterator = self._record.extended_results
        else:
            self._result_iterator = self._record.results

        self._is_started = True
        self._origin_time = None

        if self.session_config.extended:
            self._rate_stats_calc = _RateCalculator(
                self.session_config, self._record.extended_metadata
            )
        else:
            self._rate_stats_calc = _RateCalculator(self.session_config, self._record.metadata)

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        if not self.session_is_setup:
            raise ClientError("Session is not set up.")

        assert self._result_iterator is not None

        try:
            result_ = next(self._result_iterator)
            result = cast(Union[Result, List[Dict[int, Result]]], result_)
        except StopIteration:
            raise _StopReplay

        if isinstance(result, Result):
            some_result = result
        else:
            some_result = next(iter(next(iter(result)).values()))

        now = time.monotonic() - some_result.tick_time

        if self._origin_time is None:
            self._origin_time = now

        delta = now - self._origin_time

        if delta < 0:
            time.sleep(-delta)

        assert self._rate_stats_calc is not None
        self._rate_stats_calc.update(result)

        return result

    def stop_session(self) -> Any:
        self._result_iterator = None
        self._is_started = False

    def disconnect(self) -> None:
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
        return self._record.session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._record.extended_metadata

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        return self._record.calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        return self._record.calibrations_provided

    @property
    def _rate_stats(self) -> _RateStats:
        self._assert_session_started()
        assert self._rate_stats_calc is not None
        return self._rate_stats_calc.stats
