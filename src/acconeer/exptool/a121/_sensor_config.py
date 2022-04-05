from __future__ import annotations

from typing import Optional


class SubsweepConfig:
    pass


class SensorConfig:
    def __init__(
        self,
        subsweeps: Optional[list[SubsweepConfig]] = None,
        num_subsweeps: Optional[int] = None,
    ) -> None:
        if subsweeps is not None and num_subsweeps is not None:
            raise ValueError

        if subsweeps is None and num_subsweeps is None:
            num_subsweeps = 1

        if subsweeps is not None:
            self._subsweeps = subsweeps
        elif num_subsweeps is not None:
            self._subsweeps = [SubsweepConfig() for _ in range(num_subsweeps)]
        else:
            raise RuntimeError

    def _assert_single_subsweep(self) -> None:
        if self.num_subsweeps > 1:
            raise AttributeError("num_subsweeps is > 1.")

    @property
    def subsweep(self) -> SubsweepConfig:
        """Convenience attribute for accessing the one and only SubsweepConfig.

        raises an AttributeError if num_subsweeps > 1
        """
        self._assert_single_subsweep()
        return self.subsweeps[0]

    @property
    def subsweeps(self) -> list[SubsweepConfig]:
        return self._subsweeps

    @property
    def num_subsweeps(self) -> int:
        return len(self.subsweeps)

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, dict_: dict) -> SensorConfig:
        raise NotImplementedError

    def to_json(self) -> str:
        raise NotImplementedError

    @classmethod
    def from_json(cls, json_str: str) -> SensorConfig:
        raise NotImplementedError
