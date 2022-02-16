import pytest

from acconeer.exptool.a111 import Mode, get_mode


def test_special_cases():
    with pytest.raises(ValueError):
        get_mode("does-not-exist")

    with pytest.raises(ValueError):
        get_mode(object())

    assert get_mode(None) is None


@pytest.mark.parametrize("mode", Mode)
def test_positive(mode):
    assert get_mode(mode) == mode

    assert get_mode(mode.name.lower()) == mode
    assert get_mode(mode.name.upper()) == mode
    assert get_mode(mode.name.title()) == mode

    assert get_mode(mode.value.lower()) == mode
    assert get_mode(mode.value.upper()) == mode
    assert get_mode(mode.value.title()) == mode
