# Copyright (c) Acconeer AB, 2023
# All rights reserved

import typing as t
from pathlib import Path

import h5py
import pytest

from acconeer.exptool.a121._core.peripherals.h5_record import SchemaError, SessionSchema


@pytest.fixture
def empty_h5_file(tmp_file_path: Path) -> t.Iterator[h5py.File]:
    with h5py.File(tmp_file_path.with_suffix(".empty"), "x") as f:
        yield f


@pytest.fixture
def populated_h5_file(tmp_file_path: Path) -> t.Iterator[h5py.File]:
    with h5py.File(tmp_file_path.with_suffix(".populated"), "x") as f:
        # These are intentionally out of order.
        f.create_group("session_2")
        f.create_group("session_1")
        f.create_group("session_0")
        f.create_group("sessions/session_1")
        f.create_group("sessions/session_0")
        f.create_group("trash1")
        f.create_group("trash2")
        f.create_group("session")
        yield f


def test_single_lists_session_groups_on_disk_correctly(
    empty_h5_file: h5py.File,
    populated_h5_file: h5py.File,
) -> None:
    assert SessionSchema.session_groups_on_disk(empty_h5_file) == ()
    assert SessionSchema.session_groups_on_disk(populated_h5_file) == (
        populated_h5_file["session"],
    )


def test_single_creates_only_specified_sessions(empty_h5_file: h5py.File) -> None:
    assert SessionSchema.create_next_session_group(empty_h5_file) == (empty_h5_file["session"])
    with pytest.raises(SchemaError):
        _ = SessionSchema.create_next_session_group(empty_h5_file)
