# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import pytest

from acconeer.exptool import a121


def test_record_not_instantiable() -> None:
    with pytest.raises(TypeError):
        a121.Record()  # type: ignore[abstract]

    with pytest.raises(TypeError):
        a121.PersistentRecord()  # type: ignore[abstract]


def test_recorder_not_instantiable() -> None:
    with pytest.raises(TypeError):
        a121.Recorder()  # type: ignore[misc]
