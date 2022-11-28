# Copyright (c) Acconeer AB, 2022
# All rights reserved

from pathlib import Path

import attr
import h5py
import numpy as np
import pytest

from acconeer.exptool import a111
from acconeer.exptool.a111._clients.mock.client import MockClient
from acconeer.exptool.a121._core.peripherals.h5_record import _H5PY_STR_DTYPE


@pytest.fixture
def mocker():
    mocker = MockClient()
    mocker.squeeze = False
    return mocker


@pytest.mark.parametrize("mode", a111.Mode)
@pytest.mark.parametrize("ext", ["h5", "npz"])
@pytest.mark.parametrize("give_pathlib_path", [True, False])
def test_recording(tmp_path, mode, ext, give_pathlib_path, mocker):
    config = a111._configs.MODE_TO_CONFIG_CLASS_MAP[mode]()
    config.downsampling_factor = 2

    session_info = mocker.start_session(config)

    recorder = a111.recording.Recorder(
        sensor_config=config,
        session_info=session_info,
    )

    for _ in range(10):
        data_info, data = mocker.get_next()
        recorder.sample(data_info, data)

    recorder.close()
    record = recorder.record

    assert record.mode == mode
    assert record.sensor_config_dump == config._dumps()
    assert len(record.data) == 10
    assert len(record.data_info) == 10
    assert isinstance(record.data, np.ndarray)

    filename = Path(tmp_path).joinpath("record." + ext)

    if not give_pathlib_path:
        filename = str(filename)

    a111.recording.save(filename, record)
    loaded_record = a111.recording.load(filename)

    for a in attr.fields(a111.recording.Record):
        assert np.all(getattr(record, a.name) == getattr(loaded_record, a.name))

    assert record.sensor_config.downsampling_factor == config.downsampling_factor


def test_unknown_mode(mocker):
    config = a111.EnvelopeServiceConfig()
    session_info = mocker.start_session(config)
    recorder = a111.recording.Recorder(sensor_config=config, session_info=session_info)
    data_info, data = mocker.get_next()
    recorder.sample(data_info, data)
    recorder.close()
    record = recorder.record

    packed = a111.recording.pack(record)
    assert "mode" in packed

    with pytest.warns(None) as captured_warnings:
        a111.recording.unpack(packed)

    assert len(captured_warnings) == 0

    with pytest.warns(UserWarning):
        packed["mode"] = "some_unknown_mode"
        unpacked = a111.recording.unpack(packed)

    assert unpacked.mode is None


@pytest.mark.parametrize("mode", a111.Mode)
def test_packing_mode(tmp_path, mode):
    config = a111._configs.MODE_TO_CONFIG_CLASS_MAP[mode]()
    config.downsampling_factor = 2

    sensor_config_dump = config._dumps()
    session_info = {"foo": "bar"}

    record = a111.recording.Record(
        mode=mode,
        sensor_config_dump=sensor_config_dump,
        session_info=session_info,
        data=[],
        data_info=[],
    )

    packed = a111.recording.pack(record)
    restored = a111.recording.unpack(packed)

    assert restored.mode == mode


@pytest.fixture
def ref_record_file_a121(tmp_path):
    tmp_h5_path = tmp_path.with_suffix(".h5")

    file = h5py.File(tmp_h5_path, "x")
    file.create_dataset(
        "generation",
        data="a121",
        dtype=_H5PY_STR_DTYPE,
        track_times=False,
    )
    file.close()

    return tmp_h5_path


def test_open_record_a121(ref_record_file_a121):
    with pytest.raises(Exception):
        a111.recording.load(ref_record_file_a121)
