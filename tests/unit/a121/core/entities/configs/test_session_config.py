# Copyright (c) Acconeer AB, 2022
# All rights reserved

# type: ignore

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

    # Should not raise an error
    a121.SessionConfig(None)
    a121.SessionConfig()

    with pytest.raises(ValueError):
        a121.SessionConfig({1: 123})

    with pytest.raises(ValueError):
        a121.SessionConfig({"foo": a121.SensorConfig()})

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


def test_sensor_config_property():
    a_sensor_config = a121.SensorConfig()
    session_config = a121.SessionConfig(a_sensor_config)

    assert session_config.sensor_config is a_sensor_config

    session_config = a121.SessionConfig({1: a_sensor_config, 2: a121.SensorConfig()})

    with pytest.raises(Exception):
        _ = session_config.sensor_config


def test_to_dict():
    default_session_config = a121.SessionConfig(a121.SensorConfig())
    expected_dict = {
        "groups": [{1: a121.SensorConfig().to_dict()}],
        "extended": False,
        "update_rate": None,
    }

    assert expected_dict == default_session_config.to_dict()

    full_out_session_config = a121.SessionConfig(
        [{2: a121.SensorConfig(), 3: a121.SensorConfig()}], update_rate=20
    )
    expected_dict = {
        "update_rate": 20,
        "groups": [{2: a121.SensorConfig().to_dict(), 3: a121.SensorConfig().to_dict()}],
        "extended": True,
    }

    assert full_out_session_config.to_dict() == expected_dict


def test_eq():
    default_session_config = a121.SessionConfig(a121.SensorConfig())

    # Same contents means they are equal.
    assert default_session_config == a121.SessionConfig(a121.SensorConfig())

    # If a member differs in SessionConfig, they are no longer equal.
    assert default_session_config != a121.SessionConfig(a121.SensorConfig(), update_rate=1)

    # Even if a member in a contained instance differs, they should also differ.
    assert default_session_config != a121.SessionConfig(a121.SensorConfig(hwaas=42))

    # Extended will also make session configs unequal
    assert default_session_config != a121.SessionConfig(a121.SensorConfig(), extended=True)


@pytest.mark.parametrize(
    "original",
    [
        a121.SessionConfig(a121.SensorConfig()),
        a121.SessionConfig(a121.SensorConfig(hwaas=20), update_rate=1337),
    ],
)
def test_to_from_dict_and_json_identity(original):
    reconstructed = a121.SessionConfig.from_dict(original.to_dict())
    assert original == reconstructed
    reconstructed = a121.SessionConfig.from_json(original.to_json())
    assert original == reconstructed


def test_empty_init_is_the_same_as_single_sensor_config():
    assert a121.SessionConfig() == a121.SessionConfig(a121.SensorConfig())


@pytest.mark.parametrize(
    "sensor_configs",
    [
        {1: a121.SensorConfig(frame_rate=1)},
        {1: a121.SensorConfig(frame_rate=1), 2: a121.SensorConfig(frame_rate=None)},
    ],
)
def test_update_rate_in_session_config_and_frame_rate_in_any_sensor_config_is_disallowed(
    sensor_configs,
):
    config = a121.SessionConfig(sensor_configs)
    config.update_rate = 10

    with pytest.raises(a121.ValidationError):
        config.validate()
