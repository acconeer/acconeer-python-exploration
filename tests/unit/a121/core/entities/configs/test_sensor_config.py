# type: ignore

import json
import warnings

import pytest

from acconeer.exptool import a121


def test_sweeps_per_frame():
    # Default value

    config = a121.SensorConfig()
    assert config.sweeps_per_frame == 1

    # Conversion

    config.sweeps_per_frame = 2
    assert config.sweeps_per_frame == 2
    assert isinstance(config.sweeps_per_frame, int)

    config.sweeps_per_frame = 3.0
    assert config.sweeps_per_frame == 3
    assert isinstance(config.sweeps_per_frame, int)

    with pytest.raises(TypeError):
        config.sweeps_per_frame = "not-an-int"

    with pytest.raises(TypeError):
        config.sweeps_per_frame = "3"

    with pytest.raises(TypeError):
        config.sweeps_per_frame = 3.5

    config = a121.SensorConfig(sweeps_per_frame=2)
    assert config.sweeps_per_frame == 2
    assert isinstance(config.sweeps_per_frame, int)

    config = a121.SensorConfig(sweeps_per_frame=3.0)
    assert config.sweeps_per_frame == 3
    assert isinstance(config.sweeps_per_frame, int)

    with pytest.raises(TypeError):
        a121.SensorConfig(sweeps_per_frame="not-an-int")

    with pytest.raises(TypeError):
        a121.SensorConfig(sweeps_per_frame="3")

    with pytest.raises(TypeError):
        a121.SensorConfig(sweeps_per_frame=3.5)

    # Validation

    config = a121.SensorConfig()

    with pytest.raises(ValueError):
        config.sweeps_per_frame = 0

    assert config.sweeps_per_frame == 1

    with pytest.raises(ValueError):
        a121.SensorConfig(sweeps_per_frame=0)

    # Documentation

    assert a121.SensorConfig.sweeps_per_frame.__doc__


def test_subsweep_properties_read_only():
    sensor_config = a121.SensorConfig()

    with pytest.raises(AttributeError):
        sensor_config.num_subsweeps = 1

    with pytest.raises(AttributeError):
        sensor_config.subsweeps = [a121.SubsweepConfig()]


def test_implicit_subsweep():
    sensor_config = a121.SensorConfig()

    assert sensor_config.num_subsweeps == 1
    assert len(sensor_config.subsweeps) == 1


def test_init_with_hwaas():
    sc = a121.SensorConfig(hwaas=1)
    assert sc.hwaas == sc.subsweep.hwaas == 1

    with pytest.raises(ValueError):
        # This should techically be allowed, but is ambiguous as hwaas can be set
        # on in 2 places. That is why it is not allowed.
        _ = a121.SensorConfig(hwaas=1, subsweeps=[a121.SubsweepConfig()])

    with pytest.raises(AttributeError):
        _ = a121.SensorConfig(num_subsweeps=2, hwaas=1)


def test_explicit_subsweeps():
    # Should be able to explicitly give the subsweeps

    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(),
            a121.SubsweepConfig(),
        ],
    )

    assert sensor_config.num_subsweeps == 2
    assert len(sensor_config.subsweeps) == 2

    # an empty subsweeps list is not allowed
    with pytest.raises(ValueError):
        _ = a121.SensorConfig(subsweeps=[])

    # Should be able to explicitly give the number of subsweeps

    sensor_config = a121.SensorConfig(
        num_subsweeps=2,
    )

    assert sensor_config.num_subsweeps == 2
    assert len(sensor_config.subsweeps) == 2

    # Giving both subsweeps and number of subsweeps should raise a ValueError

    with pytest.raises(ValueError):
        sensor_config = a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(),
                a121.SubsweepConfig(),
            ],
            num_subsweeps=2,
        )


def test_subsweep_accessor():
    subsweep_config = a121.SubsweepConfig()
    sensor_config = a121.SensorConfig(subsweeps=[subsweep_config])

    # As long as we have a single subsweep, it should be accessible
    # through ".subsweep".
    assert sensor_config.subsweep is subsweep_config is sensor_config.subsweeps[0]

    # ... and not settable.
    with pytest.raises(Exception):
        sensor_config.subsweep = a121.SubsweepConfig()

    # When we have more than 1, an error should be raised.
    sensor_config = a121.SensorConfig(num_subsweeps=2)
    with pytest.raises(Exception):
        _ = sensor_config.subsweep

    # A docstring is nessecary to infrom the user of the raising
    # behavior.
    assert a121.SensorConfig.subsweep.__doc__


def test_single_subsweep_hwaas():
    sensor_config = a121.SensorConfig()

    # The sensor config and the (only) subsweep config should match
    assert sensor_config.hwaas == sensor_config.subsweeps[0].hwaas == sensor_config.subsweep.hwaas

    # We should be able to set values through the sensor config
    sensor_config.hwaas = 3
    assert (
        sensor_config.hwaas
        == sensor_config.subsweeps[0].hwaas
        == sensor_config.subsweep.hwaas
        == 3
    )

    # And the subsweep config
    sensor_config.subsweeps[0].hwaas = 4
    assert (
        sensor_config.hwaas
        == sensor_config.subsweeps[0].hwaas
        == sensor_config.subsweep.hwaas
        == 4
    )

    # And through single subsweep accessor
    sensor_config.subsweep.hwaas = 5
    assert (
        sensor_config.hwaas
        == sensor_config.subsweeps[0].hwaas
        == sensor_config.subsweep.hwaas
        == 5
    )


def test_num_subsweeps_creates_unique_subsweep_configs():
    sensor_config = a121.SensorConfig(num_subsweeps=2)
    assert sensor_config.subsweeps[0] is not sensor_config.subsweeps[1]


def test_multiple_subsweeps_param():
    sensor_config = a121.SensorConfig(num_subsweeps=2)

    # With multiple subsweeps, we should not be able to get/set subsweep parameters through the
    # sensor config

    with pytest.raises(Exception):
        _ = sensor_config.hwaas

    with pytest.raises(Exception):
        sensor_config.hwaas = 1


def test_single_subsweep_at_instantiation():
    sensor_config = a121.SensorConfig(
        subsweeps=[a121.SubsweepConfig(hwaas=4)],
    )

    # Make sure the subsweep is properly used
    assert sensor_config.hwaas == sensor_config.subsweeps[0].hwaas == 4


def test_eq():
    assert a121.SensorConfig() == a121.SensorConfig()
    assert a121.SensorConfig() != a121.SensorConfig(sweeps_per_frame=3)
    assert a121.SensorConfig() != a121.SensorConfig(num_subsweeps=2)
    assert a121.SensorConfig(num_subsweeps=2) == a121.SensorConfig(num_subsweeps=2)

    other = a121.SensorConfig(num_subsweeps=2)
    other.subsweeps[1].hwaas = 3
    assert a121.SensorConfig(num_subsweeps=2) != other


def test_basic_to_dict():
    # Having an explicit SubsweepConfig-dict here is out of scope as
    # SubsweepConfig.to_dict is tested in test_subsweep_config.py
    expected = {
        "sweeps_per_frame": 1,
        "sweep_rate": None,
        "frame_rate": None,
        "continuous_sweep_mode": False,
        "double_buffering": False,
        "inter_frame_idle_state": a121.IdleState.DEEP_SLEEP,
        "inter_sweep_idle_state": a121.IdleState.READY,
        "subsweeps": [a121.SubsweepConfig().to_dict()],
    }
    actual = a121.SensorConfig(sweeps_per_frame=1, subsweeps=[a121.SubsweepConfig()]).to_dict()

    assert actual == expected

    for k, expected_v in expected.items():
        if k == "subsweeps":
            continue

        assert type(actual[k]) is type(expected_v)


def test_from_to_dict():
    original_config = a121.SensorConfig(sweeps_per_frame=3)
    dict_ = original_config.to_dict()
    recreated_config = a121.SensorConfig.from_dict(dict_)
    assert recreated_config == original_config


def test_from_to_json():
    original_config = a121.SensorConfig(sweeps_per_frame=3)
    json_str = original_config.to_json()
    recreated_config = a121.SensorConfig.from_json(json_str)
    assert recreated_config == original_config


def test_enum_fields_in_to_json():
    json_str = a121.SensorConfig(
        inter_frame_idle_state=a121.IdleState.DEEP_SLEEP,
        subsweeps=[
            a121.SubsweepConfig(
                profile=a121.Profile.PROFILE_3,
            ),
        ],
    ).to_json()
    dict_from_json = json.loads(json_str)

    assert dict_from_json["inter_frame_idle_state"] == "DEEP_SLEEP"
    assert dict_from_json["subsweeps"][0]["profile"] == "PROFILE_3"


@pytest.mark.parametrize(
    ("attribute", "non_default_value"),
    [
        ("start_point", 123),
        ("num_points", 22),
        ("step_length", 24),
        ("profile", a121.Profile.PROFILE_1),
        ("hwaas", 17),
        ("receiver_gain", 13),
        ("enable_tx", False),
        ("phase_enhancement", True),
        ("prf", a121.PRF.PRF_6_5_MHz),
    ],
)
def test_get_and_set_proxy_properties(attribute, non_default_value):
    subsweep_config = a121.SubsweepConfig()
    sensor_config = a121.SensorConfig(subsweeps=[subsweep_config])

    # make sure test doesn't test default values.
    assert getattr(subsweep_config, attribute) != non_default_value
    assert getattr(sensor_config, attribute) == getattr(subsweep_config, attribute)
    setattr(sensor_config, attribute, non_default_value)
    assert getattr(sensor_config, attribute) == getattr(subsweep_config, attribute)


def test_invalid_idle_states_raises_error_upon_validate():
    config = a121.SensorConfig()
    config.inter_frame_idle_state = a121.IdleState.READY
    config.inter_sweep_idle_state = a121.IdleState.DEEP_SLEEP

    with pytest.raises(ValueError):
        config.validate()


def test_invalid_continuous_sweep_mode_constraints_raises_error_upon_validate():
    config = a121.SensorConfig()
    config.continuous_sweep_mode = True
    config.frame_rate = None
    config.sweep_rate = None  # <- should be > 0

    with pytest.raises(ValueError):
        config.validate()


def test_too_high_frame_rate_compared_to_sweep_rate_and_spf_raise_error_upon_validate():
    config = a121.SensorConfig()
    config.frame_rate = 10
    config.sweep_rate = 1
    config.sweeps_per_frame = 1

    with pytest.raises(ValueError):
        config.validate()


def test_approx_frame_rate_and_frame_time_raise_error_upon_validate():
    config = a121.SensorConfig()
    config.frame_rate = 10
    config.sweep_rate = 10
    config.sweeps_per_frame = 1

    with warnings.catch_warnings(record=True) as collected_warnings:
        config.validate()

    assert collected_warnings != []


@pytest.mark.parametrize(("num_points", "sweeps_per_frame"), [(4096, 1), (2048, 2)])
def test_config_that_require_too_much_buffer_space_raises_error_upon_validate(
    num_points, sweeps_per_frame
):
    config = a121.SensorConfig()
    config.num_points = num_points
    config.sweeps_per_frame = sweeps_per_frame

    with pytest.raises(ValueError):
        config.validate()
