import os

import attr
import numpy as np

from acconeer.exptool import clients, configs, modes, recording


def test_recording(tmp_path):
    config = configs.EnvelopeServiceConfig()
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

    assert record.mode == modes.Mode.ENVELOPE
    assert record.sensor_config_dump == config._dumps()
    assert len(record.data) == 10
    assert len(record.data_info) == 10
    assert isinstance(record.data, np.ndarray)

    for ext in ["h5", "npz"]:
        filename = os.path.join(tmp_path, "record." + ext)

        recording.save(filename, record)
        loaded_record = recording.load(filename)

        for a in attr.fields(recording.Record):
            if a.name == "data":
                continue

            assert getattr(record, a.name) == getattr(loaded_record, a.name)

        assert np.all(record.data == loaded_record.data)

    assert record.sensor_config.downsampling_factor == config.downsampling_factor
