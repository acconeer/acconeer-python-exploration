import pytest

from acconeer.exptool import a121


def test_init_default_values():
    ssc = a121.SubsweepConfig()

    assert ssc.hwaas == 8


def test_init_with_arguments():
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
def test_init_with_bad_arguments(kwargs, exception_type):
    with pytest.raises(exception_type):
        a121.SubsweepConfig(**kwargs)


@pytest.mark.xfail(reason="Not implemented yet")
def test_equals():
    assert a121.SubsweepConfig() == a121.SubsweepConfig()
    a_config = a121.SubsweepConfig(hwaas=1)
    another_config = a121.SubsweepConfig(hwaas=2)
    assert a_config != another_config


@pytest.mark.xfail(reason="Not implemented yet")
def test_to_dict():
    subsweep = a121.SubsweepConfig(hwaas=1)
    expected = {
        "hwaas": 1,
    }

    assert subsweep.to_dict() == expected  # type: ignore[attr-defined]


@pytest.mark.xfail(reason="Not implemented yet")
def test_from_dict():
    expected = a121.SubsweepConfig(hwaas=1)
    config_dict = {
        "hwaas": 1,
    }

    reconstructed = a121.SubsweepConfig.from_dict(config_dict)  # type: ignore[attr-defined]
    assert reconstructed == expected


@pytest.mark.xfail(reason="Not implemented yet")
def test_to_from_dict_identity():
    config = a121.SubsweepConfig(hwaas=42)
    reconstructed_config = a121.SubsweepConfig.from_dict(  # type: ignore[attr-defined]
        config.to_dict()  # type: ignore[attr-defined]
    )

    assert reconstructed_config == config


@pytest.mark.xfail(reason="Not implemented yet")
def test_to_from_json_identity():
    config = a121.SubsweepConfig(hwaas=42)
    reconstructed_config = a121.SubsweepConfig.from_json(  # type: ignore[attr-defined]
        config.to_json()  # type: ignore[attr-defined]
    )

    assert reconstructed_config == config
