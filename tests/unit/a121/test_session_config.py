import pytest

from acconeer.exptool import a121


def test_extended():
    session_config = a121.SessionConfig(a121.SensorConfig())
    assert session_config.extended is False

    session_config = a121.SessionConfig({1: a121.SensorConfig()})
    assert session_config.extended is False

    session_config = a121.SessionConfig([{1: a121.SensorConfig()}])
    assert session_config.extended is False

    session_config = a121.SessionConfig(a121.SensorConfig(), extended=False)
    assert session_config.extended is False

    session_config = a121.SessionConfig(a121.SensorConfig(), extended=True)
    assert session_config.extended is True

    extended_group = {2: a121.SensorConfig(), 3: a121.SensorConfig()}

    session_config = a121.SessionConfig(extended_group)
    assert session_config.extended is True

    session_config = a121.SessionConfig([extended_group])
    assert session_config.extended is True

    session_config = a121.SessionConfig(extended_group, extended=True)
    assert session_config.extended is True

    with pytest.raises(ValueError):
        a121.SessionConfig(extended_group, extended=False)


def test_update_rate():
    sensor_config = a121.SensorConfig()

    session_config = a121.SessionConfig(sensor_config)
    assert session_config.update_rate is None

    session_config.update_rate = 1.0
    assert session_config.update_rate == 1.0

    session_config.update_rate = None
    assert session_config.update_rate is None

    with pytest.raises(ValueError):
        session_config.update_rate = -1.0

    session_config = a121.SessionConfig(sensor_config, update_rate=2.0)
    assert session_config.update_rate == 2.0

    with pytest.raises(ValueError):
        a121.SessionConfig(sensor_config, update_rate=-1.0)


def test_input_checking():
    with pytest.raises(ValueError):
        a121.SessionConfig(None)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        a121.SessionConfig({1: 123})  # type: ignore[dict-item]

    with pytest.raises(ValueError):
        a121.SessionConfig({"foo": a121.SensorConfig()})  # type: ignore[dict-item]

    with pytest.raises(ValueError):
        a121.SessionConfig({})

    with pytest.raises(ValueError):
        a121.SessionConfig([])

    with pytest.raises(ValueError):
        a121.SessionConfig([{}])

    with pytest.raises(ValueError):
        a121.SessionConfig([{1: a121.SensorConfig()}, {}])


def test_sensor_id():
    session_config = a121.SessionConfig(a121.SensorConfig())
    assert session_config.sensor_id == 1

    session_config.sensor_id = 2
    assert session_config.sensor_id == 2

    session_config = a121.SessionConfig({2: a121.SensorConfig()})
    assert session_config.sensor_id == 2

    session_config = a121.SessionConfig(a121.SensorConfig(), extended=True)

    with pytest.raises(Exception):
        _ = session_config.sensor_id

    with pytest.raises(Exception):
        session_config.sensor_id = 2
