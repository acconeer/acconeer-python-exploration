import pytest

from acconeer.exptool import modes


def test_special_cases():
    with pytest.raises(ValueError):
        modes.get_mode("does-not-exist")

    with pytest.raises(ValueError):
        modes.get_mode(object())

    assert modes.get_mode(None) is None


@pytest.mark.parametrize("mode", modes.Mode)
def test_positive(mode):
    assert modes.get_mode(mode) == mode

    assert modes.get_mode(mode.name.lower()) == mode
    assert modes.get_mode(mode.name.upper()) == mode
    assert modes.get_mode(mode.name.title()) == mode

    assert modes.get_mode(mode.value.lower()) == mode
    assert modes.get_mode(mode.value.upper()) == mode
    assert modes.get_mode(mode.value.title()) == mode
