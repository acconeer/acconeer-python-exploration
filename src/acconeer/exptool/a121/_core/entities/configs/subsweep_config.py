# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
import typing as t
import warnings

import attrs

from acconeer.exptool.a121._core.utils import (
    EntityJSONEncoder,
    convert_value,
    is_divisor_of,
    is_multiple_of,
    pretty_dict_line_strs,
)

from .config_enums import PRF, Profile
from .validation_error import ValidationError, ValidationResult, ValidationWarning


SPARSE_IQ_PPC = 24

# The `converter` argument to `attrs.field` influences the signature of `__init__`
# - (https://www.attrs.org/en/stable/api.html#converters)
# This is mirrored in LSPs and the docs.
#
# `convert_value` is a generic function which needs to be specialiced to `int`s for use here
# Plain `Profile` / `PRF` functions as converters in runtime, but no type is in
# the signature of `__init__`.


def int_converter(value: int) -> int:
    return convert_value(value, factory=int)


def profile_converter(profile: Profile) -> Profile:
    return Profile(profile)


def prf_converter(prf: PRF) -> PRF:
    return PRF(prf)


@attrs.mutable(kw_only=True)
class SubsweepConfig:
    """Subsweep configuration

    The subsweep config represents a 1-1 mapping to the RSS service subsweep config.

    Normally used as a part of the :attr:`SensorConfig`.
    """

    _start_point: int = attrs.field(
        default=80,
        converter=int_converter,
    )
    _num_points: int = attrs.field(
        default=160,
        converter=int_converter,
        validator=[attrs.validators.ge(1)],
    )
    _step_length: int = attrs.field(
        default=1,
        converter=int_converter,
    )
    _profile: Profile = attrs.field(
        default=Profile.PROFILE_3,
        converter=profile_converter,
    )
    _hwaas: int = attrs.field(
        default=8,
        converter=int_converter,
        validator=[attrs.validators.ge(1), attrs.validators.le(511)],
    )
    _receiver_gain: int = attrs.field(
        default=16,
        converter=int_converter,
        validator=[attrs.validators.ge(0), attrs.validators.le(23)],
    )
    _enable_tx: bool = attrs.field(
        default=True,
        converter=bool,
    )
    _enable_loopback: bool = attrs.field(
        default=False,
        converter=bool,
    )
    _phase_enhancement: bool = attrs.field(
        default=False,
        converter=bool,
    )
    _prf: PRF = attrs.field(
        default=PRF.PRF_13_0_MHz,
        converter=prf_converter,
    )

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
            FORBIDDEN_PROFILES = [
                Profile.PROFILE_2,
                Profile.PROFILE_3,
                Profile.PROFILE_4,
                Profile.PROFILE_5,
            ]

            if self.profile in FORBIDDEN_PROFILES:
                validation_results.extend(
                    [
                        ValidationError(
                            self, "prf", "19.5 MHz PRF is only compatible with profile 1."
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
        self._start_point = value

    @property
    def num_points(self) -> int:
        """Number of data points to measure

        The number of data points to measure in a sweep.
        """

        return self._num_points

    @num_points.setter
    def num_points(self, value: int) -> None:
        self._num_points = value

    @property
    def step_length(self) -> int:
        """Step length in a sweep

        This sets the number of steps to have between each data point.

        The corresponding distance between each data point is ``step_length`` * 2.5 mm.
        """

        return self._step_length

    @step_length.setter
    def step_length(self, value: int) -> None:
        self._step_length = value

    @_step_length.validator
    def _(self, _: attrs.Attribute, step_length: int) -> None:
        if not (
            is_divisor_of(SPARSE_IQ_PPC, step_length) or is_multiple_of(SPARSE_IQ_PPC, step_length)
        ):
            raise ValueError(f"step_length must be a divisor or multiple of {SPARSE_IQ_PPC}")

    @property
    def profile(self) -> Profile:
        """Profile

        Each profile consists of a number of settings for the sensor that configures the RX and TX
        paths. Lower profiles have higher depth resolution while higher profiles have higher radar
        loop gain.
        """

        return self._profile

    @profile.setter
    def profile(self, value: Profile) -> None:
        self._profile = value

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
        self._hwaas = value

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
        self._receiver_gain = value

    @property
    def enable_tx(self) -> bool:
        """Enable or disable the transmitter

        If set to True, TX is enabled. This will enable the radio transmitter. By turning the
        transmitter off the RX noise floor can be measured.
        """

        return self._enable_tx

    @enable_tx.setter
    def enable_tx(self, value: bool) -> None:
        self._enable_tx = value

    @property
    def enable_loopback(self) -> bool:
        """Enable or disable loopback

        Enabling loopback will activate an internal route between TX and RX in the sensor.
        The signal will take this route instead of being transmitted out of the sensor.

        Note, loopback can't be enabled together with profile 2.
        """
        return self._enable_loopback

    @enable_loopback.setter
    def enable_loopback(self, value: bool) -> None:
        self._enable_loopback = value

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
        self._phase_enhancement = value

    @property
    def prf(self) -> PRF:
        """Pulse Repetition Frequency (PRF)

        Pulse Repetition Frequency, PRF, is the frequency at which pulses are sent out from
        the radar system. The measurement time is approximately proportional to the PRF.
        The higher the PRF, the shorter the measurement time.

        This parameter sets the Maximum Measurable Distance, MMD, that can be achieved. MMD is the
        maximum value for the end point, i.e., the start point + (number of points * step length).
        For example, an MMD of 7.0 m means that the range cannot be set further out than 7.0 m.

        It also sets the Maximum Unambiguous Range, MUR, that can be achieved. MUR is the maximum
        distance at which an object can be located to guarantee that its reflection corresponds to
        the most recent transmitted pulse. Objects farther away than the MUR may fold into the
        measured range. For example, with a MUR of 11.5 m, an object at 13.5 m could become
        visible at 2 m.

        ================= ======== ====== ======
        PRF Setting            PRF    MMD    MUR
        ================= ======== ====== ======
        PRF_19_5_MHZ [*]_ 19.5 MHz  3.1 m  7.7 m
        PRF_15_6_MHZ      15.6 MHz  5.8 m  9.6 m
        PRF_13_0_MHZ      13.0 MHz  7.0 m 11.5 m
        PRF_8_7_MHZ        8.7 MHz 12.7 m 17.3 m
        PRF_6_5_MHZ        6.5 MHz 18.5 m 23.1 m
        PRF_5_2_MHZ        5.2 MHz 24.2 m 28.8 m
        ================= ======== ====== ======

        .. [*] 19.5MHz is only available for profile 1.
        """

        return self._prf

    @prf.setter
    def prf(self, value: PRF) -> None:
        self._prf = PRF(value)

    def to_dict(self) -> dict[str, t.Any]:
        return {k.strip("_"): v for k, v in attrs.asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict) -> SubsweepConfig:
        return SubsweepConfig(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=EntityJSONEncoder)

    @classmethod
    def from_json(cls, json_str: str) -> SubsweepConfig:
        return cls.from_dict(json.loads(json_str))

    def _pretty_str_lines(self, index: t.Optional[int] = None) -> list[str]:
        lines = []
        index_str = "" if index is None else f" @ index {index}"
        lines.append(f"{type(self).__name__}{index_str}:")
        lines.extend(pretty_dict_line_strs(self.to_dict()))
        return lines

    def __str__(self) -> str:
        return "\n".join(self._pretty_str_lines())
