# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import copy
import datetime
import json
import time
import warnings
from pathlib import Path
from typing import Optional, Union

import attr
import h5py
import numpy as np

import acconeer.exptool as et
from acconeer.exptool._structs import configbase
from acconeer.exptool.a111 import _configs, _modes


@attr.s
class Record:
    # Sensor session related (required):
    mode = attr.ib(type=_modes.Mode)  # save as str (Mode.name), restore with get_mode
    sensor_config_dump = attr.ib(type=str)  # SensorConfig._dumps
    session_info = attr.ib(type=dict)  # save/restore with json.dumps/loads
    data = attr.ib(default=None)  # [np.array], saved as np.array, restore as is
    data_info = attr.ib(type=list, factory=list)  # [[{...}]], save/restore with json.dumps/loads

    # Processing related (optional):
    module_key = attr.ib(type=Optional[str], default=None)
    processing_config_dump = attr.ib(type=Optional[str], default=None)  # ProcessingConfig._dumps

    # Other (optional):
    rss_version = attr.ib(type=Optional[str], default=None)
    lib_version = attr.ib(type=Optional[str], default=None)
    timestamp = attr.ib(type=Optional[str], default=None)
    sample_times = attr.ib(default=None)
    note = attr.ib(type=Optional[str], default=None)  # not to be used internally

    # Legacy (optional):
    legacy_processing_config_dump = attr.ib(type=Optional[str], default=None)

    def __attrs_post_init__(self):
        self._iter_index = None

    def __iter__(self):
        self._iter_index = 0
        return self

    def __next__(self):
        try:
            current_data_info = self.data_info[self._iter_index]
            current_data = self.data[self._iter_index]
        except (IndexError, TypeError):
            raise StopIteration

        self._iter_index += 1
        return current_data_info, current_data

    @property
    def sensor_config(self):
        return _configs.load(self.sensor_config_dump, self.mode)


class Recorder:
    def __init__(self, **kwargs):
        sensor_config = kwargs.pop("sensor_config")
        session_info = kwargs.pop("session_info")
        module_key = kwargs.pop("module_key", None)
        processing_config = kwargs.pop("processing_config", None)
        rss_version = kwargs.pop("rss_version", None)

        mode = kwargs.pop("mode", sensor_config.mode)

        self.max_len = kwargs.pop("max_len", None)

        if kwargs:
            key = next(iter(kwargs.keys()))
            msg = "Recorder got an unexpected keyword argument '{}'".format(key)
            raise TypeError(msg)

        if not isinstance(sensor_config, configbase.SensorConfig):
            raise TypeError("Unexpected sensor config type")

        if isinstance(processing_config, configbase.ProcessingConfig):
            processing_config_dump = processing_config._dumps()
        elif processing_config is None:
            processing_config_dump = None
        else:
            raise TypeError("Unexpected processing config type")

        self.record = Record(
            mode=mode,
            sensor_config_dump=sensor_config._dumps(),
            session_info=copy.deepcopy(session_info),
            module_key=module_key,
            processing_config_dump=processing_config_dump,
            rss_version=rss_version,
            lib_version=et.__version__,
            timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
        )

        self.record.data = []
        self.record.sample_times = []

    def sample(self, data_info: list, data: np.ndarray):
        expected_num_dims = 3 if self.record.mode == _modes.Mode.SPARSE else 2
        if data.ndim != expected_num_dims:  # then assume data is squeezed
            # unsqueeze (add back sensor dim)
            data = data[None, ...]
            data_info = [data_info]

        self.record.data.append(data.copy())
        self.record.data_info.append(copy.deepcopy(data_info))

        self.record.sample_times.append(time.time())

        if self.max_len is not None and len(self.record.data) > self.max_len:
            self.record.data.pop(0)
            self.record.data_info.pop(0)
            self.record.sample_times.pop(0)

    def close(self):
        self.record.data = np.array(self.record.data)
        self.record.sample_times = np.array(self.record.sample_times)
        return self.record


def save(filename: Union[str, Path], record: Record):
    filename = str(filename)

    if filename.lower().endswith(".h5"):
        return save_h5(filename, record)
    elif filename.lower().endswith(".npz"):
        return save_npz(filename, record)
    elif filename.lower().endswith(".npy"):
        raise ValueError("Unknown file format '.npy', perhaps you meant '.npz'?")
    else:
        raise ValueError("Unknown file format")


def pack(record: Record) -> dict:
    packed = attr.asdict(record, filter=lambda attr, v: attr.type in (str, Optional[str]))
    packed["mode"] = record.mode.name.lower()
    packed["session_info"] = json.dumps(record.session_info)
    packed["data_info"] = json.dumps(record.data_info)

    data = np.array(record.data)
    if np.isrealobj(data):
        data_u16 = data.astype("u2")
        if np.all(data == data_u16):
            data = data_u16

    packed["data"] = data

    if record.sample_times is not None:
        packed["sample_times"] = np.array(record.sample_times)

    packed = {k: v for k, v in packed.items() if v is not None}

    return packed


def save_npz(filename: Union[str, Path], record: Record):
    filename = str(filename)

    if not filename.lower().endswith(".npz"):
        filename = filename + ".npz"

    packed = pack(record)
    np.savez_compressed(filename, **packed)


def save_h5(filename: Union[str, Path], record: Record):
    filename = str(filename)

    if not filename.lower().endswith(".h5"):
        filename = filename + ".h5"

    packed = pack(record)

    with h5py.File(filename, "w") as f:
        for k, v in packed.items():
            if isinstance(v, str):
                dtype = h5py.special_dtype(vlen=str)
                compression = None
            elif isinstance(v, np.ndarray):
                dtype = v.dtype
                compression = "gzip"
            else:
                raise TypeError

            f.create_dataset(k, data=v, dtype=dtype, compression=compression)


def load(filename: Union[str, Path]) -> Record:
    filename = str(filename)

    if filename.lower().endswith(".h5"):
        return load_h5(filename)
    elif filename.lower().endswith(".npz"):
        return load_npz(filename)
    else:
        raise ValueError("Unknown file format")


def unpack(packed: dict) -> Record:
    kwargs = {}

    data = packed["data"]
    if np.isrealobj(data):
        data = data.astype("float")

    kwargs["data"] = data

    for a in attr.fields(Record):
        k = a.name
        if a.type == str:
            kwargs[k] = packed[k]
        elif a.type == Optional[str]:
            kwargs[k] = packed.get(k, None)

    try:
        mode = _modes.get_mode(packed["mode"])
    except ValueError:
        mode = None
        warnings.warn("unknown mode encountered while unpacking record")

    kwargs["mode"] = mode

    kwargs["session_info"] = json.loads(packed["session_info"])
    kwargs["data_info"] = json.loads(packed["data_info"])

    kwargs["sample_times"] = packed.get("sample_times", None)

    assert len(kwargs["data"]) == len(kwargs["data_info"])

    return Record(**kwargs)


def load_npz(filename: Union[str, Path]) -> Record:
    filename = str(filename)

    packed = {}
    with np.load(filename, allow_pickle=False) as f:
        for k, v in f.items():
            if v.dtype.type is np.unicode_:
                v = str(v)

            packed[k] = v

    return unpack(packed)


def load_h5(filename: Union[str, Path]) -> Record:
    filename = str(filename)

    with h5py.File(filename, "r") as f:
        if "generation" in f:
            raise Exception(
                f"The file '{filename}' is not an A111 record, try a121.load_record instead"
            )
        packed = {k: v[()] for k, v in f.items()}

    for k, v in packed.items():
        if isinstance(v, bytes):
            packed[k] = v.decode()

    return unpack(packed)


if __name__ == "__main__":
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    sp = subparsers.add_parser("resave")
    sp.add_argument("source")
    sp.add_argument("dest")
    sp.add_argument("-f", "--force", action="store_true")

    args = parser.parse_args()

    # assume resave as it's currently the only option

    if not args.force and os.path.exists(args.dest):
        sys.stderr.write("error: destination file already exists (try using -f)\n")
        sys.exit(1)

    record = load(args.source)
    save(args.dest, record)
