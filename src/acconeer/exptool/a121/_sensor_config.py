from __future__ import annotations

from typing import Optional


class SubsweepConfig:
    pass


class SensorConfig:
    _sweeps_per_frame: int

    def __init__(
        self,
        subsweeps: Optional[list[SubsweepConfig]] = None,
        num_subsweeps: Optional[int] = None,
        sweeps_per_frame: int = 1,
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

        self.sweeps_per_frame = sweeps_per_frame

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

    @property
    def sweeps_per_frame(self) -> int:
        """Number of sweeps per frame (SPF).

        Must be greater than or equal to 1.
        """
        return self._sweeps_per_frame

    @sweeps_per_frame.setter
    def sweeps_per_frame(self, value: int) -> None:
        try:
            int_value = int(value)  # may raise ValueError if "value" is a non-int string
            if int_value != value:  # a float may be rounded and lose it's decimals
                raise ValueError
        except ValueError:
            raise TypeError(f"{value} cannot be fully represented as an int.")

        if int_value < 1:
            raise ValueError("sweeps_per_frame cannot be less than 1.")

        self._sweeps_per_frame = int_value
