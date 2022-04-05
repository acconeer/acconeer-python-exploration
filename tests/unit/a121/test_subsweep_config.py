import pytest

from acconeer.exptool import a121


@pytest.mark.xfail(reason="Not implemented yet")
def test_init_default_values():
    ssc = a121.SubsweepConfig()

    assert ssc.hwaas == 1  # type: ignore[attr-defined]


@pytest.mark.xfail(reason="Not implemented yet")
def test_init_with_arguments():
    ssc = a121.SubsweepConfig(hwaas=4)  # type: ignore[call-arg]

    assert ssc.hwaas == 4  # type: ignore[attr-defined]


@pytest.mark.xfail(reason="Not implemented yet")
def test_equals():
    assert a121.SubsweepConfig() == a121.SubsweepConfig()
    a_config = a121.SubsweepConfig(hwaas=1)  # type: ignore[call-arg]
    another_config = a121.SubsweepConfig(hwaas=2)  # type: ignore[call-arg]
    assert a_config != another_config


@pytest.mark.xfail(reason="Not implemented yet")
def test_to_dict():
    subsweep = a121.SubsweepConfig(hwaas=1)  # type: ignore[call-arg]
    expected = {
        "hwaas": 1,
    }

    assert subsweep.to_dict() == expected  # type: ignore[attr-defined]


@pytest.mark.xfail(reason="Not implemented yet")
def test_from_dict():
    expected = a121.SubsweepConfig(hwaas=1)  # type: ignore[call-arg]
    config_dict = {
        "hwaas": 1,
    }

    reconstructed = a121.SubsweepConfig.from_dict(config_dict)  # type: ignore[attr-defined]
    assert reconstructed == expected


@pytest.mark.xfail(reason="Not implemented yet")
def test_to_from_dict_identity():
    config = a121.SubsweepConfig(hwaas=42)  # type: ignore[call-arg]
    reconstructed_config = a121.SubsweepConfig.from_dict(  # type: ignore[attr-defined]
        config.to_dict()  # type: ignore[attr-defined]
    )

    assert reconstructed_config == config


@pytest.mark.xfail(reason="Not implemented yet")
def test_to_from_json_identity():
    config = a121.SubsweepConfig(hwaas=42)  # type: ignore[call-arg]
    reconstructed_config = a121.SubsweepConfig.from_json(  # type: ignore[attr-defined]
        config.to_json()  # type: ignore[attr-defined]
    )

    assert reconstructed_config == config
