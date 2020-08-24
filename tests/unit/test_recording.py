from pathlib import Path

import attr
import numpy as np
import pytest

from acconeer.exptool import clients, configs, modes, recording


@pytest.mark.parametrize("mode", modes.Mode)
@pytest.mark.parametrize("ext", ["h5", "npz"])
@pytest.mark.parametrize("give_pathlib_path", [True, False])
def test_recording(tmp_path, mode, ext, give_pathlib_path):
    config = configs.MODE_TO_CONFIG_CLASS_MAP[mode]()
    config.downsampling_factor = 2

    mocker = clients.MockClient()
    mocker.squeeze = False
    session_info = mocker.start_session(config)

    recorder = recording.Recorder(
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

    recording.save(filename, record)
    loaded_record = recording.load(filename)

    for a in attr.fields(recording.Record):
        assert np.all(getattr(record, a.name) == getattr(loaded_record, a.name))

    assert record.sensor_config.downsampling_factor == config.downsampling_factor


def test_unknown_mode():
    config = configs.EnvelopeServiceConfig()
    mocker = clients.MockClient()
    mocker.squeeze = False
    session_info = mocker.start_session(config)
    recorder = recording.Recorder(sensor_config=config, session_info=session_info)
    data_info, data = mocker.get_next()
    recorder.sample(data_info, data)
    recorder.close()
    record = recorder.record

    packed = recording.pack(record)
    assert "mode" in packed

    with pytest.warns(None) as captured_warnings:
        recording.unpack(packed)

    assert len(captured_warnings) == 0

    with pytest.warns(UserWarning):
        packed["mode"] = "some_unknown_mode"
        unpacked = recording.unpack(packed)

    assert(unpacked.mode is None)
