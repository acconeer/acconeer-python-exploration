from __future__ import annotations

import json
from typing import Any, Optional, TypeVar

from acconeer.exptool.a121._utils import ProxyProperty, convert_validate_int

from ._subsweep_config import SubsweepConfig


T = TypeVar("T")


class SubsweepProxyProperty(ProxyProperty[T]):
    def __init__(self, prop: Any) -> None:
        super().__init__(
            accessor=self.get_subsweep,
            prop=prop,
        )

    @staticmethod
    def get_subsweep(sensor_config: SensorConfig) -> SubsweepConfig:
        return sensor_config.subsweep


class SensorConfig:
    _sweeps_per_frame: int
    _subsweeps: list[SubsweepConfig]
    hwaas = SubsweepProxyProperty[int](SubsweepConfig.hwaas)

    def __init__(
        self,
        *,
        subsweeps: Optional[list[SubsweepConfig]] = None,
        num_subsweeps: Optional[int] = None,
        sweeps_per_frame: int = 1,
        hwaas: Optional[int] = None,
    ) -> None:
        if subsweeps is not None and num_subsweeps is not None:
            raise ValueError(
                "It's not allowed to set both subsweeps and num_subsweeps. Choose one."
            )
        if subsweeps == []:
            raise ValueError("Cannot pass an empty subsweeps list.")

        if subsweeps is not None and hwaas is not None:
            raise ValueError(
                "Combining hwaas and subsweeps is not allowed. "
                + "Specify hwaas in each SubsweepConfig instead"
            )

        if subsweeps is None and num_subsweeps is None:
            num_subsweeps = 1

        if subsweeps is not None:
            self._subsweeps = subsweeps
        elif num_subsweeps is not None:
            self._subsweeps = [SubsweepConfig() for _ in range(num_subsweeps)]
        else:
            raise RuntimeError

        self.sweeps_per_frame = sweeps_per_frame
        if hwaas is not None:
            self.hwaas = hwaas

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

    def __eq__(self, other: Any) -> bool:
        return (
            type(self) == type(other)
            and self.sweeps_per_frame == other.sweeps_per_frame
            and self.subsweeps == other.subsweeps
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sweeps_per_frame": self.sweeps_per_frame,
            "subsweeps": [subsweep.to_dict() for subsweep in self.subsweeps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SensorConfig:
        d = d.copy()
        d["subsweeps"] = [SubsweepConfig.from_dict(subsweep_d) for subsweep_d in d["subsweeps"]]
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> SensorConfig:
        return cls.from_dict(json.loads(json_str))

    @property
    def sweeps_per_frame(self) -> int:
        """Number of sweeps per frame (SPF).

        Must be greater than or equal to 1.
        """
        return self._sweeps_per_frame

    @sweeps_per_frame.setter
    def sweeps_per_frame(self, value: int) -> None:
        int_value = convert_validate_int(value, min_value=1)
        self._sweeps_per_frame = int_value
