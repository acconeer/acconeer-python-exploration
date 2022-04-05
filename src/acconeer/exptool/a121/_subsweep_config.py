from __future__ import annotations

from ._utils import convert_validate_int


class SubsweepConfig:
    def __init__(self, hwaas: int = 8) -> None:
        self.hwaas = hwaas

    @property
    def hwaas(self) -> int:
        return self._hwaas

    @hwaas.setter
    def hwaas(self, value: int) -> None:
        int_value = convert_validate_int(value, min_value=1)
        self._hwaas = int_value
