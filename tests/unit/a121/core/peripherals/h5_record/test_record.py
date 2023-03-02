# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

"""
These test doesn't look like much, but the tested member
(ref_lib_version, ref_server_info, etc.) have taken a
round-trip through:

1. Serialization
2. Saved to disk
3. Loaded through H5Record
4. Deserialization
5. ... and finally compared.
"""
from __future__ import annotations

from typing import Any, Iterator

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool import a121


def test_lib_version(ref_record: a121.Record, ref_lib_version: str) -> None:
    assert ref_record.lib_version == ref_lib_version


def test_server_info(ref_record: a121.Record, ref_server_info: a121.ServerInfo) -> None:
    assert ref_record.server_info == ref_server_info


def test_client_info(ref_record: a121.Record, ref_client_info: a121.ClientInfo) -> None:
    assert ref_record.client_info == ref_client_info


def test_session_config(ref_record: a121.Record, ref_session_config: a121.SessionConfig) -> None:
    assert ref_record.session_config == ref_session_config


def test_extended_metadata(ref_record: a121.Record, ref_metadata: a121.Metadata) -> None:
    for group in ref_record.extended_metadata:
        for _sensor_id, metadata in group.items():
            assert metadata == ref_metadata


def test_timestamp(ref_record: a121.Record, ref_timestamp: str) -> None:
    assert ref_record.timestamp == ref_timestamp


def test_uuid(ref_record: a121.Record, ref_uuid: str) -> None:
    assert ref_record.uuid == ref_uuid


def test_data_layout(ref_record: a121.H5Record, ref_structure: Iterator[Iterator[int]]) -> None:
    assert [set(d.keys()) for d in ref_record._get_entries()] == ref_structure


def test_extended_results(
    ref_record: a121.Record, ref_frame_raw: npt.NDArray[Any], ref_frame: npt.NDArray[np.complex_]
) -> None:
    for measurement in ref_record.extended_results:
        for group in measurement:
            for _sensor_id, result in group.items():
                np.testing.assert_array_equal(result._frame, ref_frame_raw)
                np.testing.assert_array_equal(result.frame, ref_frame)


def test_num_frames(ref_record: a121.Record, ref_num_frames: int) -> None:
    assert ref_record.num_frames == ref_num_frames


def test_stacked_results_num_frames(
    ref_record: a121.Record, ref_num_frames: int, ref_structure: Iterator[Iterator[int]]
) -> None:
    for group_id, group in enumerate(ref_structure):
        for sensor_id in group:
            assert len(ref_record.extended_stacked_results[group_id][sensor_id]) == ref_num_frames


def test_stacked_results_data(
    ref_record: a121.Record,
    ref_frame: npt.NDArray[np.complex_],
    ref_structure: Iterator[Iterator[int]],
) -> None:
    for group_id, group in enumerate(ref_structure):
        for sensor_id in group:
            for frame in ref_record.extended_stacked_results[group_id][sensor_id].frame:
                np.testing.assert_array_equal(frame, ref_frame)


def test_sensor_id(ref_record: a121.Record, ref_structure: Iterator[Iterator[int]]) -> None:
    if ref_structure == [{1}]:
        assert ref_record.sensor_id == 1
    else:
        with pytest.raises(ValueError):
            _ = ref_record.sensor_id
