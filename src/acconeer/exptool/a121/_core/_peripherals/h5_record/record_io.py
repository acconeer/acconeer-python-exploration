from __future__ import annotations

import os
from typing import Union

import h5py

from acconeer.exptool.a121._core._entities import PersistentRecord, Record

from .record import H5Record
from .recorder import H5Recorder


def open_record(path_or_file: Union[os.PathLike, h5py.File]) -> PersistentRecord:
    if isinstance(path_or_file, os.PathLike):
        path = path_or_file
        file = h5py.File(path, "r")
    elif isinstance(path_or_file, h5py.File):
        file = path_or_file
    else:
        raise TypeError

    return H5Record(file)


def load_record(path_or_file: Union[os.PathLike, h5py.File]) -> Record:
    raise NotImplementedError


def save_record(path_or_file: Union[os.PathLike, h5py.File], record: Record) -> None:
    return save_record_to_h5(path_or_file, record)


def save_record_to_h5(path_or_file: Union[os.PathLike, h5py.File], record: Record) -> None:
    recorder = H5Recorder(path_or_file)

    recorder.start(
        client_info=record.client_info,
        extended_metadata=record.extended_metadata,
        server_info=record.server_info,
        session_config=record.session_config,
    )

    for extended_result in record.extended_results:
        recorder.sample(extended_result)

    recorder.stop()
