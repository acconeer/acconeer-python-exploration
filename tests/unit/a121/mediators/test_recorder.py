import pytest

from acconeer.exptool import a121


def test_recorder_not_instantiable():
    with pytest.raises(Exception):
        a121.Recorder()  # type: ignore[misc]
