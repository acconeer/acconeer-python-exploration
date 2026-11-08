# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import RecordException


_RESULT_DATASETS = [
    "data_saturated",
    "frame_delayed",
    "calibration_needed",
    "temperature",
    "tick",
    "frame",
]
_CALIBRATION_DATASETS = ["temperature", "data", "provided"]


def test_close_h5_record(tmp_file_path: Path) -> None:
    file = h5py.File(tmp_file_path, "x")
    file.create_dataset(
        "generation",
        data="a121",
        dtype=a121._H5PY_STR_DTYPE,
        track_times=False,
    )
    try:
        record = a121.open_record(file)
        assert file
        record.close()
        assert not file
    finally:
        file.close()


def test_open_record(ref_record_file: Path) -> None:
    with a121.open_record(ref_record_file) as ref_record:
        assert isinstance(ref_record, a121.H5Record)


def test_load_record(ref_record_file: Path) -> None:
    ref_record = a121.load_record(ref_record_file)
    assert isinstance(ref_record, a121.InMemoryRecord)


@pytest.fixture
def ref_record_file_a111(tmp_file_path: Path) -> Path:
    tmp_h5_path = tmp_file_path.with_suffix(".h5")

    file = h5py.File(tmp_h5_path, "x")
    file.close()

    return tmp_h5_path


def test_open_record_a111(ref_record_file_a111: Path) -> None:
    with pytest.raises(a121.RecordError), a121.open_record(ref_record_file_a111) as _:
        pass


def test_can_save_record(ref_record: a121.Record, tmp_file_path: Path) -> None:
    a121.save_record(tmp_file_path.with_suffix(".copy"), ref_record)


def _session_groups(f: h5py.File) -> list[h5py.Group]:
    return [f[f"sessions/session_{i}"] for i in range(len(f["sessions"]))]


def _entries_by_sensor(session_group: h5py.Group) -> dict[tuple[int, int], h5py.Group]:
    entries = {}
    for group_name, group in session_group.items():
        if group_name.startswith("group_"):
            for entry in group.values():
                entries[(int(group_name.split("_")[1]), int(entry["sensor_id"][()]))] = entry
    return entries


@pytest.fixture(
    params=[(), (0, 1), (0,), (1,)],
    ids=lambda s: f"uncalibrated_sessions={list(s)}",
)
def distinct_record_file(
    ref_record_file: Path, request: pytest.FixtureRequest
) -> tuple[Path, list[bool]]:
    """ref_record_file with distinct values per session, group and sensor, and with
    calibrations removed from the sessions given by the parameter
    """
    calibrated = []
    with h5py.File(ref_record_file, "r+") as f:
        for s, session_group in enumerate(_session_groups(f)):
            for (group_idx, sensor_id), entry in _entries_by_sensor(session_group).items():
                result = entry["result"]
                offset = 100 * s + 10 * group_idx + sensor_id
                pattern = np.arange(result["tick"].shape[0]) + offset
                result["tick"][...] = pattern
                result["temperature"][...] = -pattern
                result["data_saturated"][...] = pattern % 2 == 0
                result["frame_delayed"][...] = pattern % 3 == 0
                result["calibration_needed"][...] = pattern % 5 == 0
                frame = result["frame"][()]
                frame["real"] += offset
                frame["imag"] -= offset
                result["frame"][...] = frame

            for name, calibration in session_group["calibrations"].items():
                sensor_id = int(name.split("_")[1])
                calibration["temperature"][()] = 20 + 10 * s + sensor_id
                calibration["provided"][()] = (s + sensor_id) % 2 == 0

            is_calibrated = s not in request.param
            if not is_calibrated:
                del session_group["calibrations"]
            calibrated.append(is_calibrated)

    return ref_record_file, calibrated


def _assert_public_copy(source_path: Path, copy_path: Path, calibrated: list[bool]) -> None:
    with a121.open_record(source_path) as source, a121.open_record(copy_path) as copy:
        assert copy.client_info == source.client_info
        assert copy.server_info == source.server_info
        assert copy.num_sessions == source.num_sessions == len(calibrated)

        for i in range(source.num_sessions):
            source_session = source.session(i)
            copy_session = copy.session(i)

            assert copy_session.session_config == source_session.session_config
            assert copy_session.num_frames == source_session.num_frames
            # Group count, sensor IDs per group and metadata. Together with server_info,
            # this is all that result contexts are built from.
            assert copy_session.extended_metadata == source_session.extended_metadata

            if calibrated[i]:
                assert copy_session.calibrations_provided == source_session.calibrations_provided
                assert copy_session.calibrations.keys() == source_session.calibrations.keys()
            else:
                with pytest.raises(RecordException):
                    _ = copy_session.calibrations
                with pytest.raises(RecordException):
                    _ = copy_session.calibrations_provided


def _assert_stored_copy(source_path: Path, copy_path: Path, calibrated: list[bool]) -> None:
    with h5py.File(source_path, "r") as source_file, h5py.File(copy_path, "r") as copy_file:
        source_sessions = _session_groups(source_file)
        copy_sessions = _session_groups(copy_file)
        assert len(copy_sessions) == len(source_sessions) == len(calibrated)

        for source_session, copy_session, is_calibrated in zip(
            source_sessions, copy_sessions, calibrated
        ):
            source_entries = _entries_by_sensor(source_session)
            copy_entries = _entries_by_sensor(copy_session)
            assert set(copy_entries) == set(source_entries)

            for key, source_entry in source_entries.items():
                for name in _RESULT_DATASETS:
                    np.testing.assert_array_equal(
                        copy_entries[key][f"result/{name}"][()],
                        source_entry[f"result/{name}"][()],
                        err_msg=f"{key} result/{name}",
                    )

            assert ("calibrations" in source_session) is is_calibrated
            assert ("calibrations" in copy_session) is is_calibrated
            if is_calibrated:
                source_calibrations = source_session["calibrations"]
                copy_calibrations = copy_session["calibrations"]
                assert set(copy_calibrations.keys()) == set(source_calibrations.keys())

                for sensor_name, source_calibration in source_calibrations.items():
                    for name in _CALIBRATION_DATASETS:
                        assert (
                            copy_calibrations[sensor_name][name][()]
                            == source_calibration[name][()]
                        ), f"{sensor_name}/{name}"


@pytest.mark.parametrize("loader", ["load_record", "open_record"])
def test_save_record_round_trip(
    distinct_record_file: tuple[Path, list[bool]], tmp_file_path: Path, loader: str
) -> None:
    source_path, calibrated = distinct_record_file
    copy_path = tmp_file_path.with_suffix(".copy")

    if loader == "load_record":
        a121.save_record(copy_path, a121.load_record(source_path))
    else:
        with a121.open_record(source_path) as record:
            a121.save_record(copy_path, record)

    _assert_public_copy(source_path, copy_path, calibrated)
    _assert_stored_copy(source_path, copy_path, calibrated)


def test_save_record_does_not_swallow_corrupt_calibrations(
    ref_record_file: Path, tmp_file_path: Path
) -> None:
    with h5py.File(ref_record_file, "r+") as f:
        for session_group in _session_groups(f):
            for calibration in session_group["calibrations"].values():
                del calibration["provided"]

    with a121.open_record(ref_record_file) as record, pytest.raises(KeyError):
        a121.save_record(tmp_file_path.with_suffix(".copy"), record)
