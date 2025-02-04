# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

import json
from typing import Any

import pytest

from acconeer.exptool import a121


def test_init_default_values() -> None:
    ssc = a121.SubsweepConfig()

    assert ssc.hwaas == 8


def test_init_with_arguments() -> None:
    ssc = a121.SubsweepConfig(hwaas=4)
    assert ssc.hwaas == 4


@pytest.mark.parametrize(
    ("kwargs", "exception_type"),
    [
        (dict(hwaas="1"), TypeError),
        (dict(hwaas=3.5), TypeError),
        (dict(hwaas=0), ValueError),
        (dict(hwaas=-1), ValueError),
    ],
)
def test_init_with_bad_arguments(kwargs: Any, exception_type: Any) -> None:
    with pytest.raises(exception_type):
        a121.SubsweepConfig(**kwargs)


def test_equals() -> None:
    assert a121.SubsweepConfig() == a121.SubsweepConfig()
    a_config = a121.SubsweepConfig(hwaas=1)
    another_config = a121.SubsweepConfig(hwaas=2)
    assert a_config != another_config


def test_to_dict_defaults() -> None:
    subsweep = a121.SubsweepConfig()
    expected = {
        "start_point": 80,
        "num_points": 160,
        "step_length": 1,
        "profile": a121.Profile.PROFILE_3,
        "hwaas": 8,
        "receiver_gain": 16,
        "enable_tx": True,
        "enable_loopback": False,
        "phase_enhancement": False,
        "iq_imbalance_compensation": False,
        "prf": a121.PRF.PRF_15_6_MHz,
    }

    assert subsweep.to_dict() == expected

    for k, expected_v in expected.items():
        assert type(subsweep.to_dict()[k]) is type(expected_v)


def test_from_dict() -> None:
    expected = a121.SubsweepConfig(hwaas=1)
    config_dict = {
        "hwaas": 1,
    }

    reconstructed = a121.SubsweepConfig.from_dict(config_dict)
    assert reconstructed == expected


def test_to_from_dict_identity() -> None:
    config = a121.SubsweepConfig(hwaas=42)
    reconstructed_config = a121.SubsweepConfig.from_dict(config.to_dict())

    assert reconstructed_config == config


def test_to_from_json_identity() -> None:
    config = a121.SubsweepConfig(hwaas=42)
    reconstructed_config = a121.SubsweepConfig.from_json(config.to_json())

    assert reconstructed_config == config


def test_prf_field_in_json_representation_is_a_string_that_can_be_converted_back() -> None:
    config = a121.SubsweepConfig(prf=a121.PRF.PRF_8_7_MHz)

    json_dict = json.loads(config.to_json())

    enum_member_name = json_dict["prf"]
    assert enum_member_name == "PRF_8_7_MHz"
    assert isinstance(enum_member_name, str)
    assert a121.PRF(enum_member_name) in a121.PRF


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_length": 7},
        {"step_length": 13},
        {"step_length": 25},
    ],
)
def test_bad_step_lengths(kwargs: Any) -> None:
    with pytest.raises(ValueError):
        _ = a121.SubsweepConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_length": 1},
        {"step_length": 2},
        {"step_length": 3},
        {"step_length": 6},
        {"step_length": 12},
        {"step_length": 24},
        {"step_length": 48},
    ],
)
def test_step_length(kwargs: Any) -> None:
    _ = a121.SubsweepConfig(**kwargs)


def test_setting_enum_parameters() -> None:
    conf = a121.SubsweepConfig()

    # These 2 should be valid

    conf.prf = a121.PRF.PRF_13_0_MHz

    conf.prf = "PRF_13_0_MHz"  # type: ignore[assignment]

    # But something like this should not be.
    RSS_KEY = 1
    with pytest.raises(ValueError):
        conf.prf = RSS_KEY  # type: ignore[assignment]


def test_bad_loopback_and_profile_combination() -> None:
    conf = a121.SubsweepConfig(profile=a121.Profile.PROFILE_2, enable_loopback=True)
    with pytest.raises(a121.ValidationError):
        conf.validate()


@pytest.mark.parametrize(
    "profile",
    [
        a121.Profile.PROFILE_3,
        a121.Profile.PROFILE_4,
        a121.Profile.PROFILE_5,
    ],
)
def test_bad_prf_and_profile_combination(profile: a121.Profile) -> None:
    conf = a121.SubsweepConfig(profile=profile, prf=a121.PRF.PRF_19_5_MHz)
    with pytest.raises(a121.ValidationError):
        conf.validate()


def test_validation_is_run_on_set() -> None:
    conf = a121.SubsweepConfig()
    conf.hwaas = 1.0  # type: ignore[assignment]

    with pytest.raises(TypeError):
        conf.hwaas = "1"  # type: ignore[assignment]

    assert conf.hwaas != "1"

    with pytest.raises(ValueError):
        conf.hwaas = -1


def test_prf_property_has_same_docstring_as_enum() -> None:
    assert a121.SubsweepConfig.prf.__doc__ == a121.PRF.__doc__
