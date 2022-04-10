import pytest

from acconeer.exptool import a121


def test_record_not_instantiable():
    with pytest.raises(Exception):
        a121.Record()  # type: ignore[abstract]


def test_recorder_not_instantiable():
    with pytest.raises(Exception):
        a121.Recorder()  # type: ignore[misc]
