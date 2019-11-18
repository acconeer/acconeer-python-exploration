import pytest

from acconeer.exptool import modes


def test_get_modes():
    with pytest.raises(ValueError):
        modes.get_mode("does-not-exist")

    with pytest.raises(ValueError):
        modes.get_mode(object())

    assert modes.get_mode(None) is None
    assert modes.get_mode("sparse") == modes.Mode.SPARSE
    assert modes.get_mode("SPARSE") == modes.Mode.SPARSE
    assert modes.get_mode(modes.Mode.SPARSE) == modes.Mode.SPARSE
