# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from pathlib import Path

import h5py
import pytest

from acconeer.exptool import a121


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


@pytest.mark.parametrize("generation", ["a2", "a211"])
def test_open_record_a2_points_to_a2_loader(tmp_file_path: Path, generation: str) -> None:
    with h5py.File(tmp_file_path, "x") as file:
        file.create_dataset("generation", data=generation, dtype=a121._H5PY_STR_DTYPE)

    with pytest.raises(a121.RecordError, match=r"a2\.open_record"):
        a121.open_record(tmp_file_path)


def test_open_record_unknown_generation_names_it(tmp_file_path: Path) -> None:
    with h5py.File(tmp_file_path, "x") as file:
        file.create_dataset("generation", data="a3", dtype=a121._H5PY_STR_DTYPE)

    with pytest.raises(a121.RecordError, match=r"generation 'a3'"):
        a121.open_record(tmp_file_path)
