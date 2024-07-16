# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

from typing import Iterator, Optional, Sequence

import attrs

from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Record,
    RecordException,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
    SessionRecord,
    StackedResults,
)


class InMemoryRecordException(Exception):
    pass


@attrs.frozen(kw_only=True)
class InMemorySessionRecord(SessionRecord):
    extended_metadata: list[dict[int, Metadata]]
    extended_stacked_results: list[dict[int, StackedResults]]
    num_frames: int
    session_config: SessionConfig
    _calibrations: Optional[dict[int, SensorCalibration]]
    _calibrations_provided: Optional[dict[int, bool]]

    @property
    def extended_results(self) -> Iterator[list[dict[int, Result]]]:
        for frame_no in range(self.num_frames):
            yield self._get_result_for_all_entries(frame_no)

    @property
    def sensor_id(self) -> int:
        return self.session_config.sensor_id

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        if self._calibrations is None:
            msg = "No calibration in record"
            raise InMemoryRecordException(msg)
        return self._calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        if self._calibrations_provided is None:
            msg = "No calibration in record"
            raise InMemoryRecordException(msg)
        return self._calibrations_provided

    def _get_result_for_all_entries(self, frame_no: int) -> list[dict[int, Result]]:
        def stacked_results_to_result(stacked_results: StackedResults) -> Result:
            return stacked_results[frame_no]

        return utils.map_over_extended_structure(
            stacked_results_to_result, self.extended_stacked_results
        )

    @classmethod
    def from_session_record(cls, session_record: SessionRecord) -> InMemorySessionRecord:
        try:
            calibrations = session_record.calibrations
            calibrations_provided = session_record.calibrations_provided
        except RecordException:
            calibrations = None
            calibrations_provided = None

        return cls(
            extended_metadata=session_record.extended_metadata,
            extended_stacked_results=session_record.extended_stacked_results,
            num_frames=session_record.num_frames,
            session_config=session_record.session_config,
            calibrations=calibrations,
            calibrations_provided=calibrations_provided,
        )


@attrs.frozen(kw_only=True)
class InMemoryRecord(Record):
    client_info: ClientInfo
    lib_version: str
    server_info: ServerInfo
    timestamp: str
    uuid: str
    _sessions: Sequence[InMemorySessionRecord]

    def session(self, session_index: int) -> InMemorySessionRecord:
        return self._sessions[session_index]

    @property
    def num_sessions(self) -> int:
        return len(self._sessions)

    @classmethod
    def from_record(cls, record: Record) -> InMemoryRecord:
        return cls(
            client_info=record.client_info,
            lib_version=record.lib_version,
            server_info=record.server_info,
            timestamp=record.timestamp,
            uuid=record.uuid,
            sessions=tuple(
                InMemorySessionRecord.from_session_record(record.session(i))
                for i in range(record.num_sessions)
            ),
        )
