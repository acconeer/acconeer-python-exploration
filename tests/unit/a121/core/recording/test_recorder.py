# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import pytest

from acconeer.exptool import a121


def test_recorder_not_instantiable() -> None:
    with pytest.raises(TypeError):
        a121.Recorder()  # type: ignore[misc]
