import copy
import datetime
import json
from typing import Optional

import attr
import h5py
import numpy as np

import acconeer.exptool
import acconeer.exptool.structs.configbase as cb
from acconeer.exptool import configs, modes


@attr.s
class Record:
    # Sensor session related (required):
    mode = attr.ib(type=modes.Mode)               # save as str (Mode.name), restore with get_mode
    sensor_config_dump = attr.ib(type=str)        # cb._dumps
    session_info = attr.ib(type=dict)             # save/restore with json.dumps/loads
    data = attr.ib(default=None)                  # [np.array], saved as np.array, restore as is
    data_info = attr.ib(type=list, factory=list)  # [[{...}]], save/restore with json.dumps/loads

    # Processing related (optional):
    module_key = attr.ib(type=Optional[str], default=None)
    processing_config_dump = attr.ib(type=Optional[str], default=None)  # cb._dumps

    # Other (optional):
    rss_version = attr.ib(type=Optional[str], default=None)
    lib_version = attr.ib(type=Optional[str], default=None)
    timestamp = attr.ib(type=Optional[str], default=None)

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
        config = configs.MODE_TO_CONFIG_CLASS_MAP[self.mode]()
        config._loads(self.sensor_config_dump)
        return config


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

        if not isinstance(sensor_config, cb.SensorConfig):
            raise TypeError("Unexpected sensor config type")

        if isinstance(processing_config, cb.ProcessingConfig):
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
            lib_version=acconeer.exptool.__version__,
            timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
        )

        self.record.data = []

    def sample(self, data_info: list, data: np.ndarray):  # should be unsqueezed
        self.record.data.append(data.copy())
        self.record.data_info.append(copy.deepcopy(data_info))

        if self.max_len is not None and len(self.record.data) > self.max_len:
            self.record.data.pop(0)
            self.record.data_info.pop(0)

    def close(self):
        self.record.data = np.array(self.record.data)


def save(filename: str, record: Record):
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
    packed["data"] = np.array(record.data)
    packed["data_info"] = json.dumps(record.data_info)

    packed = {k: v for k, v in packed.items() if v is not None}

    return packed


def save_npz(filename: str, record: Record):
    if not filename.lower().endswith(".npz"):
        filename = filename + ".npz"

    packed = pack(record)
    np.savez(filename, **packed)


def save_h5(filename: str, record: Record):
    if not filename.lower().endswith(".h5"):
        filename = filename + ".h5"

    packed = pack(record)

    with h5py.File(filename, "w") as f:
        for k, v in packed.items():
            if isinstance(v, str):
                dtype = h5py.special_dtype(vlen=str)
            elif isinstance(v, np.ndarray):
                dtype = v.dtype
            else:
                raise TypeError

            f.create_dataset(k, data=v, dtype=dtype)


def load(filename: str) -> Record:
    if filename.lower().endswith(".h5"):
        return load_h5(filename)
    elif filename.lower().endswith(".npz"):
        return load_npz(filename)
    else:
        raise ValueError("Unknown file format")


def unpack(packed: dict) -> Record:
    kwargs = {}

    for a in attr.fields(Record):
        k = a.name
        if a.type == str:
            kwargs[k] = packed[k]
        elif a.type == Optional[str]:
            kwargs[k] = packed.get(k, None)

    kwargs["mode"] = modes.get_mode(packed["mode"])
    kwargs["session_info"] = json.loads(packed["session_info"])
    kwargs["data"] = packed["data"]
    kwargs["data_info"] = json.loads(packed["data_info"])

    return Record(**kwargs)


def load_npz(filename: str) -> Record:
    f = np.load(filename)

    packed = {}
    for k in f.files:
        v = f[k]

        if v.dtype.type is np.unicode_:
            v = str(v)

        packed[k] = v

    return unpack(packed)


def load_h5(filename: str) -> Record:
    with h5py.File(filename, "r") as f:
        packed = {k: v[()] for k, v in f.items()}

    return unpack(packed)
