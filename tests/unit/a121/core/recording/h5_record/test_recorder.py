# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from pathlib import Path
from typing import Optional

import h5py
import pytest

import acconeer.exptool
from acconeer.exptool import a121
from acconeer.exptool.utils import get_module_version


def assert_record_equals(record_a: a121.Record, record_b: a121.Record) -> None:
    attrs = [
        "lib_version",
        "server_info",
        "timestamp",
        "uuid",
    ]
    for attr in attrs:
        attr_a = getattr(record_a, attr)
        attr_b = getattr(record_b, attr)

        assert attr_a == attr_b, f".{attr} differs:\n{attr_a},\n{attr_b}"

    session_attrs = [
        "extended_metadata",
        "extended_results",
        "num_frames",
        "session_config",
    ]
    assert record_a.num_sessions == record_b.num_sessions
    for session_idx in range(record_a.num_sessions):
        session_a = record_a.session(session_idx)
        session_b = record_b.session(session_idx)

        for attr in session_attrs:
            attr_a = getattr(session_a, attr)
            attr_b = getattr(session_b, attr)
            if attr == "extended_results":
                attr_a = list(attr_a)
                attr_b = list(attr_b)

            assert attr_a == attr_b, f".{attr} differs:\n{attr_a},\n{attr_b}"


def test_init_defaults_with_path(tmp_file_path: Path) -> None:
    recorder = a121.H5Recorder(tmp_file_path)
    assert recorder.owns_file is True
    assert recorder.path == tmp_file_path

    with h5py.File(tmp_file_path, "r") as f:
        assert f["lib_version"][()].decode() == get_module_version(acconeer.exptool)
        assert f["generation"][()].decode() == "a121"


def test_init_defaults_with_file_object(tmp_file_path: Path) -> None:
    with h5py.File(tmp_file_path, "x") as f:
        recorder = a121.H5Recorder(f)
        assert recorder.owns_file is False
        assert recorder.path is None
        assert f["lib_version"][()].decode() == get_module_version(acconeer.exptool)
        assert f["generation"][()].decode() == "a121"


def test_start_can_only_be_called_once(
    tmp_file_path: Path,
    ref_client_info: a121.ClientInfo,
    ref_server_info: a121.ServerInfo,
) -> None:
    r = a121.H5Recorder(tmp_file_path)
    r._start(client_info=ref_client_info, server_info=ref_server_info)

    with pytest.raises(Exception):
        r._start(client_info=ref_client_info, server_info=ref_server_info)


@pytest.mark.parametrize("chunk_size", [None, 1, 512])
def test_sample_whole_record(
    tmp_path: Path, ref_record: a121.Record, chunk_size: Optional[int]
) -> None:
    filename = tmp_path / "empty.h5"
    with a121.H5Recorder(
        filename,
        _lib_version=ref_record.lib_version,
        _timestamp=ref_record.timestamp,
        _uuid=ref_record.uuid,
        _chunk_size=chunk_size,
    ) as recorder:
        recorder._start(
            client_info=ref_record.client_info,
            server_info=ref_record.server_info,
        )

        assert ref_record.num_sessions > 0
        for i in range(ref_record.num_sessions):
            session = ref_record.session(i)
            recorder._start_session(
                session_config=session.session_config,
                extended_metadata=session.extended_metadata,
                calibrations=session.calibrations,
                calibrations_provided=session.calibrations_provided,
            )

            for extended_results in session.extended_results:
                recorder._sample(extended_results)

            recorder._stop_session()

    with a121.open_record(filename) as record:
        assert_record_equals(record, ref_record)

    record = a121.load_record(filename)
    assert_record_equals(record, ref_record)
