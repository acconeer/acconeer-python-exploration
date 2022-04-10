from __future__ import annotations

import os
from typing import Union

import h5py

from ._record import PersistentRecord, Record


def open_record(path_or_file: Union[os.PathLike, h5py.File]) -> PersistentRecord:
    raise NotImplementedError


def load_record(path_or_file: Union[os.PathLike, h5py.File]) -> Record:
    raise NotImplementedError


def save_record(path_or_file: Union[os.PathLike, h5py.File], record: Record) -> None:
    return save_record_to_h5(path_or_file, record)


def save_record_to_h5(path_or_file: Union[os.PathLike, h5py.File], record: Record) -> None:
    raise NotImplementedError
