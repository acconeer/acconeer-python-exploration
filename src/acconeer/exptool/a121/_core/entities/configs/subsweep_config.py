# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import json
import typing as t
import warnings

import attrs
from attributes_doc import attributes_doc

from acconeer.exptool import opser
from acconeer.exptool._core.class_creation.formatting import pretty_dict_line_strs
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from acconeer.exptool.a121._core.utils import (
    EntityJSONEncoder,
    convert_value,
    is_divisor_of,
    is_multiple_of,
)

from .config_enums import PRF, Profile


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


_T = t.TypeVar("_T")


def _copy_docstring_from(thing: t.Any) -> t.Callable[[_T], _T]:
    """Modifies the decorated function by copying over the __doc__ of `thing`"""

    def inner(decoratee: _T) -> _T:
        decoratee.__doc__ = thing.__doc__
        return decoratee

    return inner


@attributes_doc
@attrs.mutable(kw_only=True)
class SubsweepConfig:
    """Subsweep configuration

    The subsweep config represents a 1-1 mapping to the RSS service subsweep config.

    Normally used as a part of the :attr:`SensorConfig`. Multiple group configurations are required
    when certain parameters cannot be configured in subsweep config.
    """

    MAX_HWAAS = 511

    start_point: int = attrs.field(default=80, converter=int_converter)
    """Starting point of the sweep

    The starting point of the sweep. The corresponding start in millimeter is approximately
    ``start_point`` * 2.5 mm.
    """

    num_points: int = attrs.field(
        default=160,
        converter=int_converter,
        validator=[attrs.validators.ge(1)],
    )
    """Number of data points to measure

    The number of data points to measure in a sweep.
    """

    step_length: int = attrs.field(default=1, converter=int_converter)
    """Step length in a sweep

    This sets the number of steps to have between each data point.

    The corresponding distance between each data point is ``step_length`` * 2.5 mm.
    """

    profile: Profile = attrs.field(default=Profile.PROFILE_3, converter=profile_converter)
    """Profile

    Each profile consists of a number of settings for the sensor that configures the RX and TX
    paths. Lower profiles have higher depth resolution while higher profiles have higher radar
    loop gain.
    """

    hwaas: int = attrs.field(
        default=8,
        converter=int_converter,
        validator=[attrs.validators.ge(1), attrs.validators.le(511)],
    )
    """Hardware accelerated average samples (HWAAS)

    Each data point can be sampled several times and the sensor hardware then produces an
    average value of those samples. The time needed to measure a sweep is roughly proportional
    to the number of averaged samples. Hence, if there is a need to obtain a higher update
    rate, HWAAS could be decreased but this leads to lower SNR.

    HWAAS must be between 1 and 511 inclusive.
    """

    receiver_gain: int = attrs.field(
        default=16,
        converter=int_converter,
        validator=[attrs.validators.ge(0), attrs.validators.le(23)],
    )
    """Receiver gain setting

    Must be a value between 0 and 23 inclusive where 23 is the highest gain and 0 the lowest.

    Lower gain gives higher SNR. However, too low gain may result in quantization, lowering
    SNR. Too high gain may result in saturation, corrupting the data.
    """

    enable_tx: bool = attrs.field(default=True, converter=bool)
    """Enable or disable the transmitter

    If set to True, TX is enabled. This will enable the radio transmitter. By turning the
    transmitter off the RX noise floor can be measured.
    """

    enable_loopback: bool = attrs.field(default=False, converter=bool)
    """Enable or disable loopback

    Enabling loopback will activate an internal route between TX and RX in the sensor.
    The signal will take this route instead of being transmitted out of the sensor.

    Note, loopback can't be enabled together with profile 2.
    """

    phase_enhancement: bool = attrs.field(default=False, converter=bool)
    """Enable or disable phase enhancement

    If enabled, the data phase will be enhanced such that coherent distance filtering can be
    applied. Given a single reflection from an object, the phase will appear as "flat" around
    the amplitude peak.

    Enabling the phase enhancement increases the processing execution time.
    """

    iq_imbalance_compensation: bool = attrs.field(default=False, converter=bool)
    """Enable or disable IQ imbalance compensation

    If enabled, reduces undesirable amplitude variations over distance.

    Enabling IQ imbalance compensation increases the processing execution time.
    """

    _prf: PRF = attrs.field(
        default=PRF.PRF_15_6_MHz,
        converter=prf_converter,
    )

    @property
    @_copy_docstring_from(PRF)
    def prf(self) -> PRF:
        return self._prf

    @prf.setter
    def prf(self, value: PRF) -> None:
        self._prf = PRF(value)

    def _collect_validation_results(self) -> list[ValidationResult]:
        APPROX_BASE_STEP_LENGTH = 2.5e-3
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

        end_point_m = (
            self.start_point + ((self.num_points - 1) * self.step_length)
        ) * APPROX_BASE_STEP_LENGTH
        if end_point_m > self.prf.maximum_measurable_distance:
            validation_results.extend(
                [
                    ValidationError(
                        self,
                        "prf",
                        f"PRF is too high for the measuring end point ({end_point_m:.3f}m), "
                        + "try lowering the PRF.",
                    ),
                    ValidationError(
                        self,
                        "num_points",
                        f"Measuring range is too long for PRF (max {self.prf.mmd:.2f}m), "
                        + "try decreasing the number of points.",
                    ),
                    ValidationError(
                        self,
                        "step_length",
                        f"Measuring range is too long for PRF (max {self.prf.mmd:.2f}m), "
                        + "try decreasing the step length.",
                    ),
                ]
            )

        if self.start_point < -275:
            validation_results.append(
                ValidationError(
                    self,
                    "start_point",
                    "Start point must be larger than or equal to -275",
                )
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

    @staticmethod
    @step_length.validator
    def step_length_validator(instance: t.Any, _: t.Any, step_length: int) -> None:
        if not (
            is_divisor_of(SPARSE_IQ_PPC, step_length) or is_multiple_of(SPARSE_IQ_PPC, step_length)
        ):
            msg = f"Step length must be a divisor or multiple of {SPARSE_IQ_PPC}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, t.Any]:
        return {k.strip("_"): v for k, v in attrs.asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, t.Any]) -> SubsweepConfig:
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


opser.register_json_presentable(SubsweepConfig)
