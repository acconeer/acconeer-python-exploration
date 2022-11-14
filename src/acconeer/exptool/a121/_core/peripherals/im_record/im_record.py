# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Iterator, Optional

import attrs

from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Record,
    RecordException,
    Result,
    SensorCalibration,
    ServerInfo,
    SessionConfig,
    StackedResults,
)


class InMemoryRecordException(Exception):
    pass


@attrs.frozen(kw_only=True)
class InMemoryRecord(Record):
    _client_info: ClientInfo = attrs.field()
    _extended_metadata: list[dict[int, Metadata]] = attrs.field()
    _extended_stacked_results: list[dict[int, StackedResults]] = attrs.field()
    _lib_version: str = attrs.field()
    _num_frames: int = attrs.field()
    _server_info: ServerInfo = attrs.field()
    _session_config: SessionConfig = attrs.field()
    _timestamp: str = attrs.field()
    _uuid: str = attrs.field()
    _calibrations: Optional[dict[int, SensorCalibration]] = attrs.field()
    _calibrations_provided: Optional[dict[int, bool]] = attrs.field()

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._extended_metadata

    @property
    def extended_results(self) -> Iterator[list[dict[int, Result]]]:
        for frame_no in range(self.num_frames):
            yield self._get_result_for_all_entries(frame_no)

    def _get_result_for_all_entries(self, frame_no: int) -> list[dict[int, Result]]:
        def stacked_results_to_result(stacked_results: StackedResults) -> Result:
            return stacked_results[frame_no]

        return utils.map_over_extended_structure(
            stacked_results_to_result, self._extended_stacked_results
        )

    @property
    def extended_stacked_results(self) -> list[dict[int, StackedResults]]:
        return self._extended_stacked_results

    @property
    def lib_version(self) -> str:
        return self._lib_version

    @property
    def num_frames(self) -> int:
        return self._num_frames

    @property
    def server_info(self) -> ServerInfo:
        return self._server_info

    @property
    def session_config(self) -> SessionConfig:
        return self._session_config

    @property
    def sensor_id(self) -> int:
        return self._session_config.sensor_id

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @property
    def uuid(self) -> str:
        return self._uuid

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        if self._calibrations is None:
            raise InMemoryRecordException("No calibration in record")
        return self._calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        if self._calibrations_provided is None:
            raise InMemoryRecordException("No calibration in record")
        return self._calibrations_provided

    @classmethod
    def from_record(cls, record: Record) -> InMemoryRecord:
        try:
            calibrations = record.calibrations
            calibrations_provided = record.calibrations_provided
        except RecordException:
            calibrations = None
            calibrations_provided = None

        return cls(
            client_info=record.client_info,
            extended_metadata=record.extended_metadata,
            extended_stacked_results=record.extended_stacked_results,
            lib_version=record.lib_version,
            num_frames=record.num_frames,
            server_info=record.server_info,
            session_config=record.session_config,
            timestamp=record.timestamp,
            uuid=record.uuid,
            calibrations=calibrations,
            calibrations_provided=calibrations_provided,
        )
