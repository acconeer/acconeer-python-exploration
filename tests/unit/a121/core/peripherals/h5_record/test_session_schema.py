# Copyright (c) Acconeer AB, 2023
# All rights reserved

import typing as t
from pathlib import Path

import h5py
import pytest

from acconeer.exptool.a121._core.peripherals.h5_record import SessionSchema


@pytest.fixture
def empty_h5_file(tmp_file_path: Path) -> t.Iterator[h5py.File]:
    with h5py.File(tmp_file_path.with_suffix(".empty"), "x") as f:
        yield f


@pytest.fixture
def new_schema_h5_file(tmp_file_path: Path) -> t.Iterator[h5py.File]:
    with h5py.File(tmp_file_path.with_suffix(".new_schema"), "x") as f:
        # These are intentionally out of order.
        f.create_group("session_2")
        f.create_group("session_1")
        f.create_group("session_0")
        f.create_group("sessions/session_1")
        f.create_group("sessions/session_0")
        f.create_group("sessions/session_2")
        f.create_group("trash1")
        f.create_group("trash2")
        f["session"] = h5py.SoftLink("sessions/session_0")
        yield f


@pytest.fixture
def old_schema_h5_file(tmp_file_path: Path) -> t.Iterator[h5py.File]:
    with h5py.File(tmp_file_path.with_suffix(".old_schema"), "x") as f:
        # These are intentionally out of order.
        f.create_group("session_1")
        f.create_group("trash1")
        f.create_group("trash2")
        f.create_group("session")
        yield f


def test_lists_session_groups_on_disk_correctly(
    empty_h5_file: h5py.File, new_schema_h5_file: h5py.File, old_schema_h5_file: h5py.File
) -> None:
    assert SessionSchema.session_groups_on_disk(empty_h5_file) == ()

    assert SessionSchema.session_groups_on_disk(new_schema_h5_file) == (
        new_schema_h5_file["sessions/session_0"],
        new_schema_h5_file["sessions/session_1"],
        new_schema_h5_file["sessions/session_2"],
    )

    assert SessionSchema.session_groups_on_disk(old_schema_h5_file) == (
        old_schema_h5_file["session"],
    )


def test_creates_only_specified_sessions(empty_h5_file: h5py.File) -> None:
    assert (
        SessionSchema.create_next_session_group(empty_h5_file)
        == empty_h5_file["sessions/session_0"]
    )
    assert (
        SessionSchema.create_next_session_group(empty_h5_file)
        == empty_h5_file["sessions/session_1"]
    )
    assert (
        SessionSchema.create_next_session_group(empty_h5_file)
        == empty_h5_file["sessions/session_2"]
    )
    assert (
        SessionSchema.create_next_session_group(empty_h5_file)
        == empty_h5_file["sessions/session_3"]
    )


def test_creates_a_soft_link_together_with_the_first_group(empty_h5_file: h5py.File) -> None:
    SessionSchema.create_next_session_group(empty_h5_file)
    assert isinstance(empty_h5_file.get("session", getlink=True), h5py.SoftLink)
