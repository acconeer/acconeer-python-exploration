from __future__ import annotations

import json
from typing import Any

import attrs

from acconeer.exptool.a121._core.utils import (
    EntityJSONEncoder,
    convert_validate_int,
    is_divisor_of,
    is_multiple_of,
)

from .config_enums import PRF, Profile


SPARSE_IQ_PPC = 24


@attrs.define(init=False)
class SubsweepConfig:
    """Subsweep configuration

    The subsweep config represents a 1-1 mapping to the RSS service subsweep config.

    Normally used as a part of the :attr:`SensorConfig`.
    """

    _start_point: int
    _num_points: int
    _step_length: int
    _profile: Profile
    _hwaas: int
    _receiver_gain: int
    _enable_tx: bool
    _phase_enhancement: bool
    _prf: PRF

    def __init__(
        self,
        *,
        start_point: int = 80,
        num_points: int = 160,
        step_length: int = 1,
        profile: Profile = Profile.PROFILE_3,
        hwaas: int = 8,
        receiver_gain: int = 16,
        enable_tx: bool = True,
        phase_enhancement: bool = False,
        prf: PRF = PRF.PRF_13_0_MHz,
    ) -> None:
        self.__attrs_init__(  # type: ignore[attr-defined]
            start_point=start_point,
            num_points=num_points,
            step_length=step_length,
            profile=profile,
            hwaas=hwaas,
            receiver_gain=receiver_gain,
            enable_tx=enable_tx,
            phase_enhancement=phase_enhancement,
            prf=prf,
        )
        self.start_point = start_point
        self.num_points = num_points
        self.step_length = step_length
        self.profile = profile
        self.hwaas = hwaas
        self.receiver_gain = receiver_gain
        self.enable_tx = enable_tx
        self.phase_enhancement = phase_enhancement
        self.prf = prf

    def validate(self) -> None:
        """Performs self-validation

        :raises ValueError: If anything is invalid.
        """

    @property
    def start_point(self) -> int:
        """The starting point of the sweep."""
        return self._start_point

    @start_point.setter
    def start_point(self, value: int) -> None:
        self._start_point = convert_validate_int(value)

    @property
    def num_points(self) -> int:
        """Number of data points to measure."""
        return self._num_points

    @num_points.setter
    def num_points(self, value: int) -> None:
        self._num_points = convert_validate_int(value, min_value=1)

    @property
    def step_length(self) -> int:
        """The step length."""
        return self._step_length

    @step_length.setter
    def step_length(self, value: int) -> None:
        step_length = convert_validate_int(value)

        if not (
            is_divisor_of(SPARSE_IQ_PPC, step_length) or is_multiple_of(SPARSE_IQ_PPC, step_length)
        ):
            raise ValueError(f"step_length must be a divisor or multiple of {SPARSE_IQ_PPC}")

        self._step_length = step_length

    @property
    def profile(self) -> Profile:
        """The currently used profile"""
        return self._profile

    @profile.setter
    def profile(self, value: Profile) -> None:
        self._profile = Profile(value)

    @property
    def hwaas(self) -> int:
        """Hardware accelerated average samples."""
        return self._hwaas

    @hwaas.setter
    def hwaas(self, value: int) -> None:
        self._hwaas = convert_validate_int(value, min_value=1, max_value=511)

    @property
    def receiver_gain(self) -> int:
        """Receiver gain setting."""
        return self._receiver_gain

    @receiver_gain.setter
    def receiver_gain(self, value: int) -> None:
        self._receiver_gain = convert_validate_int(value, min_value=0, max_value=23)

    @property
    def enable_tx(self) -> bool:
        """Enable or disable the transmitter."""
        return self._enable_tx

    @enable_tx.setter
    def enable_tx(self, value: bool) -> None:
        self._enable_tx = bool(value)

    @property
    def phase_enhancement(self) -> bool:
        """Phase enhancement setting."""
        return self._phase_enhancement

    @phase_enhancement.setter
    def phase_enhancement(self, value: bool) -> None:
        self._phase_enhancement = bool(value)

    @property
    def prf(self) -> PRF:
        """Pulse repetition frequency."""
        return self._prf

    @prf.setter
    def prf(self, value: PRF) -> None:
        self._prf = PRF(value)

    def to_dict(self) -> dict[str, Any]:
        return {k.strip("_"): v for k, v in attrs.asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict) -> SubsweepConfig:
        return SubsweepConfig(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=EntityJSONEncoder)

    @classmethod
    def from_json(cls, json_str: str) -> SubsweepConfig:
        return cls.from_dict(json.loads(json_str))
