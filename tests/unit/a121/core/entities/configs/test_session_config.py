# Copyright (c) Acconeer AB, 2022-2026
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


@pytest.mark.parametrize(
    "groups",
    [
        [{1: a121.SensorConfig(frame_rate=1)}, {2: a121.SensorConfig()}],
        [{1: a121.SensorConfig(frame_rate=1)}, {2: a121.SensorConfig(frame_rate=2)}],
    ],
)
def test_frame_rate_with_multiple_groups_is_disallowed(groups):
    config = a121.SessionConfig(groups)

    with pytest.raises(a121.ValidationError):
        config.validate()


def test_frame_rate_with_single_group_multiple_sensors_is_allowed():
    config = a121.SessionConfig({1: a121.SensorConfig(frame_rate=1), 2: a121.SensorConfig()})

    config.validate()


def test_invalid_attribute():
    config = a121.SessionConfig()
    config.update_rate = 10

    with pytest.raises(AttributeError, match="Invalid attribute*"):
        config.update_ratee = 10


@pytest.mark.parametrize(
    ("groups", "message"),
    [
        ([], "groups must hold at least one group"),
        ({}, "a group must hold at least one sensor"),
        (
            (a121.SensorConfig(),),
            "groups must be a SensorConfig, a dict of sensor id to SensorConfig, "
            "or a list of such dicts; got tuple",
        ),
        ({1: "x"}, "sensor 1 maps to str, not SensorConfig"),
        ([{1: a121.SubsweepConfig()}], "sensor 1 maps to SubsweepConfig, not SensorConfig"),
    ],
    ids=["empty-list", "empty-dict", "tuple", "non-sensorconfig", "subsweepconfig"],
)
def test_malformed_groups_error_says_what_is_wrong(groups, message):
    with pytest.raises(ValueError, match=message):
        a121.SessionConfig(groups)


def test_non_int_sensor_id_error_says_what_was_given():
    with pytest.raises(ValueError, match="sensor id must be an int; got str"):
        a121.SessionConfig({"1": a121.SensorConfig()})


def test_list_of_sensor_configs_error_says_groups_are_dicts():
    with pytest.raises(
        ValueError, match="a group must be a dict of sensor id to SensorConfig; got SensorConfig"
    ):
        a121.SessionConfig([a121.SensorConfig(), a121.SensorConfig()])
