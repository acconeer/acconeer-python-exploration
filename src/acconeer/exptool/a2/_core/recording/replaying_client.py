# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import itertools
import time
import typing as t
import warnings

from acconeer.exptool._core.communication.client import ClientError
from acconeer.exptool.a2._core.communication.client import Client as A2Client
from acconeer.exptool.a2._core.entities import GroupResult, Metadata, ServerInfo, SessionConfig

from .h5_record import H5Record


class ReplayingClient(A2Client, register=False):
    def __init__(
        self,
        record: H5Record,
        *,
        realtime_replay: bool = True,
        cycled_session_idx: t.Optional[int] = None,
    ) -> None:
        super().__init__(record.client_info)
        self.record = record
        self.realtime_replay = realtime_replay
        self.result_iterator: t.Iterator[GroupResult] = iter([])
        self.replay_start_time: t.Optional[float] = None
        self.first_result_tick: t.Optional[int] = None

        if cycled_session_idx is None:
            self.session_index_iter = iter(range(record.num_sessions))
        else:
            self.session_index_iter = itertools.repeat(cycled_session_idx)

        self.current_session_index: t.Optional[int] = next(self.session_index_iter)

    def setup_session(
        self, config: SessionConfig, calibration: t.Optional[str] = None
    ) -> Metadata:
        if calibration is not None:
            warnings.warn("ReplayingClient will ignore passed calibrations", stacklevel=2)

        self._assert_connected()

        if self.current_session_index is None:
            msg = "Sessions in internal record have been exhausted"
            raise ClientError(msg)

        expected_config = self.record.session(self.current_session_index).session_config

        if config != expected_config:
            raise ValueError

        self._config = config

        self._metadata = self.record.session(self.current_session_index).metadata

        return self._metadata

    def start_session(self) -> None:
        self._assert_session_setup()

        if self.current_session_index is None:
            msg = "Sessions in internal record have been exhausted"
            raise ClientError(msg)

        self.replay_start_time = time.perf_counter()
        self.result_iterator = self.record.session(self.current_session_index).group_results
        self._session_is_started = True

    def stop_session(self) -> None:
        super().stop_session()
        self.current_session_index = next(self.session_index_iter, None)

    def _get_next_group_result(self) -> GroupResult:
        self._assert_session_started()
        assert self.replay_start_time is not None
        group_result = next(self.result_iterator)

        if self.realtime_replay:
            self._sleep_until_result_is_ripe(group_result)

        return group_result

    def _sleep_until_result_is_ripe(self, group_result: GroupResult) -> None:
        assert self.replay_start_time is not None
        first_result = group_result.results[0]

        if self.first_result_tick is None:
            self.first_result_tick = first_result.tick
            return

        result_seconds_since_session_start = first_result.seconds_since_tick(
            self.server_info.ticks_per_second,
            tick=self.first_result_tick,
        )

        seconds_since_replay_start = time.perf_counter() - self.replay_start_time

        if result_seconds_since_session_start > seconds_since_replay_start:
            time.sleep(result_seconds_since_session_start - seconds_since_replay_start)

    @property
    def server_info(self) -> ServerInfo:
        self._assert_connected()
        return self.record.server_info

    def close(self) -> None:
        self._closed = True

    @property
    def connected(self) -> bool:
        return not self._closed
