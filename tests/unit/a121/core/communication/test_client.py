# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from acconeer.exptool import a121
from acconeer.exptool._core.communication.client import ClientCreationError


@pytest.mark.parametrize("generation", ["a111", "a2"])
def test_open_with_other_generation_names_the_generation(generation: str) -> None:
    with pytest.raises(ClientCreationError, match=f"generation='{generation}'"):
        a121.Client.open(mock=True, generation=generation)
