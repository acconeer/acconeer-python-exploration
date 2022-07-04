from __future__ import annotations

import json
import warnings
from typing import Any, Optional

import attrs

from acconeer.exptool.a121._core.utils import (
    EntityJSONEncoder,
    convert_validate_int,
    is_divisor_of,
    is_multiple_of,
    pretty_dict_line_strs,
)

from .config_enums import PRF, Profile
from .validation_error import ValidationError, ValidationResult, ValidationWarning


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
    _enable_loopback: bool
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
        enable_loopback: bool = False,
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
            enable_loopback=enable_loopback,
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
        self.enable_loopback = enable_loopback
        self.phase_enhancement = phase_enhancement
        self.prf = prf

    def _collect_validation_results(self) -> list[ValidationResult]:
        validation_results: list[ValidationResult] = []

        if self.enable_loopback and self.profile == Profile.PROFILE_2:
            validation_results.extend(
                [
                    ValidationError(
                        self, "enable_loopback", "Enable loopback is incompatible with Profile 2."
                    ),
                    ValidationError(
                        self, "profile", "Enable loopback is incompatible with Profile 2."
                    ),
                ]
            )

        if self.prf == PRF.PRF_19_5_MHz:
            FORBIDDEN_PROFILES = [Profile.PROFILE_3, Profile.PROFILE_4, Profile.PROFILE_5]

            if self.profile in FORBIDDEN_PROFILES:
                validation_results.extend(
                    [
                        ValidationError(
                            self, "prf", "19.5 MHz PRF is only compatible with profile 1 and 2."
                        ),
                        ValidationError(
                            self,
                            "profile",
                            f"Profile {self.profile.value} is not supported with 19.5 MHz PRF.",
                        ),
                    ]
                )

        return validation_results

    def validate(self) -> None:
        """Performs self-validation

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)

    @property
    def start_point(self) -> int:
        """Starting point of the sweep

        The starting point of the sweep. The corresponding start in millimeter is approximately
        ``start_point`` * 2.5 mm.
        """

        return self._start_point

    @start_point.setter
    def start_point(self, value: int) -> None:
        self._start_point = convert_validate_int(value)

    @property
    def num_points(self) -> int:
        """Number of data points to measure

        The number of data points to measure in a sweep.
        """

        return self._num_points

    @num_points.setter
    def num_points(self, value: int) -> None:
        self._num_points = convert_validate_int(value, min_value=1)

    @property
    def step_length(self) -> int:
        """Step length in a sweep

        This sets the number of steps to have between each data point.

        Sampling produces complex (IQ) data points with configurable distance spacing, starting
        from ~2.5mm.
        """

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
        """Profile

        Each profile consists of a number of settings for the sensor that configures the RX and TX
        paths. Lower profiles have higher depth resolution while higher profiles have higher radar
        loop gain.

        See also :class:`Profile`.
        """

        return self._profile

    @profile.setter
    def profile(self, value: Profile) -> None:
        self._profile = Profile(value)

    @property
    def hwaas(self) -> int:
        """Hardware accelerated average samples (HWAAS)

        Each data point can be sampled several times and the sensor hardware then produces an
        average value of those samples. The time needed to measure a sweep is roughly proportional
        to the number of averaged samples. Hence, if there is a need to obtain a higher update
        rate, HWAAS could be decreased but this leads to lower SNR.

        HWAAS must be between 1 and 511 inclusive.
        """

        return self._hwaas

    @hwaas.setter
    def hwaas(self, value: int) -> None:
        self._hwaas = convert_validate_int(value, min_value=1, max_value=511)

    @property
    def receiver_gain(self) -> int:
        """Receiver gain setting

        Must be a value between 0 and 23 inclusive where 23 is the highest gain and 0 the lowest.

        Lower gain gives higher SNR. However, too low gain may result in quantization, lowering
        SNR. Too high gain may result in saturation, corrupting the data.
        """

        return self._receiver_gain

    @receiver_gain.setter
    def receiver_gain(self, value: int) -> None:
        self._receiver_gain = convert_validate_int(value, min_value=0, max_value=23)

    @property
    def enable_tx(self) -> bool:
        """Enable or disable the transmitter

        If set to True, TX is enabled. This will enable the radio transmitter. By turning the
        transmitter off the RX noise floor can be measured.
        """

        return self._enable_tx

    @enable_tx.setter
    def enable_tx(self, value: bool) -> None:
        self._enable_tx = bool(value)

    @property
    def enable_loopback(self) -> bool:
        """Enable or disable loopback

        Note, loopback can't be enabled together with profile 2.
        """
        return self._enable_loopback

    @enable_loopback.setter
    def enable_loopback(self, value: bool) -> None:
        self._enable_loopback = bool(value)

    @property
    def phase_enhancement(self) -> bool:
        """Enable or disable phase enhancement

        If enabled, the data phase will be enhanced such that coherent distance filtering can be
        applied. Given a single reflection from an object, the phase will appear as "flat" around
        the amplitude peak.

        Enabling the phase enhancement increases the processing execution time.
        """

        return self._phase_enhancement

    @phase_enhancement.setter
    def phase_enhancement(self, value: bool) -> None:
        self._phase_enhancement = bool(value)

    @property
    def prf(self) -> PRF:
        """Pulse Repetition Frequency (PRF)

        See :class:`PRF` for details.
        """

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

    def _pretty_str_lines(self, index: Optional[int] = None) -> list[str]:
        lines = []
        index_str = "" if index is None else f" @ index {index}"
        lines.append(f"{type(self).__name__}{index_str}:")
        lines.extend(pretty_dict_line_strs(self.to_dict()))
        return lines

    def __str__(self) -> str:
        return "\n".join(self._pretty_str_lines())
