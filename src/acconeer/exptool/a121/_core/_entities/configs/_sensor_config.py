from __future__ import annotations

import json
from typing import Any, Optional, TypeVar

from acconeer.exptool.a121._core._utils import ProxyProperty, convert_validate_int

from ._subsweep_config import SubsweepConfig
from .config_enums import PRF, Profile


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

    start_point = SubsweepProxyProperty[int](SubsweepConfig.start_point)
    num_points = SubsweepProxyProperty[int](SubsweepConfig.num_points)
    step_length = SubsweepProxyProperty[int](SubsweepConfig.step_length)
    profile = SubsweepProxyProperty[Profile](SubsweepConfig.profile)
    hwaas = SubsweepProxyProperty[int](SubsweepConfig.hwaas)
    receiver_gain = SubsweepProxyProperty[int](SubsweepConfig.receiver_gain)
    enable_tx = SubsweepProxyProperty[bool](SubsweepConfig.enable_tx)
    phase_enhancement = SubsweepProxyProperty[bool](SubsweepConfig.phase_enhancement)
    prf = SubsweepProxyProperty[PRF](SubsweepConfig.prf)

    def __init__(
        self,
        *,
        subsweeps: Optional[list[SubsweepConfig]] = None,
        num_subsweeps: Optional[int] = None,
        sweeps_per_frame: int = 1,
        start_point: Optional[int] = None,
        num_points: Optional[int] = None,
        step_length: Optional[int] = None,
        profile: Optional[Profile] = None,
        hwaas: Optional[int] = None,
        receiver_gain: Optional[int] = None,
        enable_tx: Optional[bool] = None,
        phase_enhancement: Optional[bool] = None,
        prf: Optional[PRF] = None,
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

        # Init proxy attributes

        if hwaas is not None:
            self.hwaas = hwaas
        if start_point is not None:
            self.start_point = start_point
        if num_points is not None:
            self.num_points = num_points
        if step_length is not None:
            self.step_length = step_length
        if profile is not None:
            self.profile = profile
        if receiver_gain is not None:
            self.receiver_gain = receiver_gain
        if enable_tx is not None:
            self.enable_tx = enable_tx
        if phase_enhancement is not None:
            self.phase_enhancement = phase_enhancement
        if prf is not None:
            self.prf = prf

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
