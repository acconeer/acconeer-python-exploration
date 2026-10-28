# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import math
import typing as t
import warnings

import attrs
import attrs.converters as ac
import attrs.validators as av
import typing_extensions as te
from attributes_doc import attributes_doc

import acconeer.exptool.type_migration as tm
from acconeer.exptool._core.class_creation.descriptors import Descriptor, delegate_field
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)

from .config_enums import PRF, IdleState, Profile
from .subsweep_config import SubsweepConfig, subsweep_config_timeline


_T = t.TypeVar("_T")

_TOO_MANY_SUBSWEEPS_ERROR_FORMAT = (
    "SensorConfig has too many subsweeps "
    + 'to use accessor "{}". '
    + 'Specify a specific subsweep with ".subsweeps[x]".'
)


def subsweep_delegate_field(
    descriptor: _T | Descriptor[_T],
    type_: type[_T],
) -> Descriptor[_T]:
    return delegate_field(
        "subsweep",
        descriptor,
        type_=type_,
        doc=SubsweepConfig,
        error_format=_TOO_MANY_SUBSWEEPS_ERROR_FORMAT.format("{descriptor_name}"),
    )


MIN_SWEEPS_PER_FRAME = 1
MAX_SWEEPS_PER_FRAME = 512

MIN_SWEEP_RATE = 8e-4
MIN_FRAME_RATE = 8e-4


@attributes_doc
@attrs.mutable
class SensorConfig(AttrsMappingTransformsMixin):
    _DEFAULT_SPF = 1
    _DEFAULT_SWEEP_RATE = None
    _DEFAULT_FRAME_RATE = None
    _DEFAULT_IDLE_STATE = IdleState.ARMED
    _DEFAULT_JITTER_COMPENSATION = True

    MAX_NUM_SUBSWEEPS = 5

    subsweeps: list[SubsweepConfig] = attrs.field(
        validator=[
            av.deep_iterable(av.instance_of(SubsweepConfig)),
            av.min_len(1),
            av.max_len(MAX_NUM_SUBSWEEPS),
        ]
    )
    """The list of subsweep configs"""

    sweeps_per_frame: int = attrs.field(
        validator=[av.ge(MIN_SWEEPS_PER_FRAME), av.le(MAX_SWEEPS_PER_FRAME)]
    )
    """
    Sets the number of sweeps that will be captured in each frame(measurement).
    Can be set to 0 if e.g. only temperature measurement is wanted.
    """

    sweep_rate: float | None = attrs.field(
        converter=ac.optional(float), validator=av.optional(av.gt(MIN_SWEEP_RATE))
    )
    """The rate for sweeps in a frame (measurement) in Hz.

    Must be > 0 or ``None``, where ``None`` is interpreted as max sweep rate.
    """

    frame_rate: float | None = attrs.field(
        converter=ac.optional(float), validator=av.optional(av.gt(MIN_FRAME_RATE))
    )
    """The frame rate in Hz.

    Must be > 0 or ``None``, where ``None`` is interpreted as max frame rate.
    """

    inter_frame_idle_state: IdleState = attrs.field(converter=IdleState)
    """The inter frame idle state is the state the sensor idles in between each frame."""

    inter_sweep_idle_state: IdleState = attrs.field(converter=IdleState)
    """The inter sweep idle state is the state the sensor idles in between each sweep in a frame."""

    jitter_compensation: bool = attrs.field(converter=bool)
    """Enable jitter compensation"""

    start_point = subsweep_delegate_field(SubsweepConfig.start_point, type_=int)
    num_points = subsweep_delegate_field(SubsweepConfig.num_points, type_=int)
    step_length = subsweep_delegate_field(SubsweepConfig.step_length, type_=int)
    profile = subsweep_delegate_field(SubsweepConfig.profile, type_=Profile)
    prf = subsweep_delegate_field(SubsweepConfig.prf, type_=PRF)
    tx_antenna_mask = subsweep_delegate_field(SubsweepConfig.tx_antenna_mask, type_=int)
    rx_antenna_mask = subsweep_delegate_field(SubsweepConfig.rx_antenna_mask, type_=int)

    @classmethod
    def default(cls) -> SensorConfig:
        """Creates a default SensorConfig"""
        return cls.single_subsweep()

    @classmethod
    def single_subsweep(
        cls,
        *,
        sweeps_per_frame: int = _DEFAULT_SPF,
        sweep_rate: float | None = _DEFAULT_SWEEP_RATE,
        frame_rate: float | None = _DEFAULT_FRAME_RATE,
        inter_frame_idle_state: IdleState = _DEFAULT_IDLE_STATE,
        inter_sweep_idle_state: IdleState = _DEFAULT_IDLE_STATE,
        jitter_compensation: bool = _DEFAULT_JITTER_COMPENSATION,
        **subsweep_parameters: t.Any,
    ) -> SensorConfig:
        """Creates a SensorConfig with a single :class:`SubsweepConfig`,

        The ``subsweep_parameters`` are sent directly to :class:`SubsweepConfig`'s constructor.

        Examples:

        >>> SensorConfig.single_subsweep()
        SensorConfig(subsweeps=[SubsweepConfig(start_point=100, num_points=40, step_length=16, ...)], sweeps_per_frame=1, ...)
        >>> SensorConfig.single_subsweep(sweeps_per_frame=3, start_point=20)
        SensorConfig(subsweeps=[SubsweepConfig(start_point=20,...)],
                     sweeps_per_frame=3,
                     ...)
        """
        return cls.identical_subsweeps(
            num_subsweeps=1,
            sweeps_per_frame=sweeps_per_frame,
            sweep_rate=sweep_rate,
            frame_rate=frame_rate,
            inter_frame_idle_state=inter_frame_idle_state,
            inter_sweep_idle_state=inter_sweep_idle_state,
            jitter_compensation=jitter_compensation,
            **subsweep_parameters,
        )

    @classmethod
    def identical_subsweeps(
        cls,
        *,
        num_subsweeps: int,
        sweeps_per_frame: int = _DEFAULT_SPF,
        sweep_rate: float | None = _DEFAULT_SWEEP_RATE,
        frame_rate: float | None = _DEFAULT_FRAME_RATE,
        inter_frame_idle_state: IdleState = _DEFAULT_IDLE_STATE,
        inter_sweep_idle_state: IdleState = _DEFAULT_IDLE_STATE,
        jitter_compensation: bool = _DEFAULT_JITTER_COMPENSATION,
        **subsweep_parameters: t.Any,
    ) -> SensorConfig:
        """Creates a :class:`SensorConfig` with ``num_subsweeps`` identical subsweeps.

        Examples:

        >>> SensorConfig.identical_subsweeps(num_subsweeps=2, num_points=37)
        SensorConfig(subsweeps=[SubsweepConfig(...,
                                               num_points=37,
                                               ...),
                                SubsweepConfig(...,
                                               num_points=37,
                                               ...)],
                     sweeps_per_frame=1,
                     ...)
        """
        return cls(
            [SubsweepConfig(**subsweep_parameters) for _ in range(num_subsweeps)],
            sweeps_per_frame=sweeps_per_frame,
            sweep_rate=sweep_rate,
            frame_rate=frame_rate,
            inter_frame_idle_state=inter_frame_idle_state,
            inter_sweep_idle_state=inter_sweep_idle_state,
            jitter_compensation=jitter_compensation,
        )

    @property
    def subsweep(self) -> SubsweepConfig:
        """Get the sole subsweep config.

        :raise AttributeError: if there is more than 1 subsweep.

        >>> config = SensorConfig.identical_subsweeps(num_subsweeps=2)
        >>> config.subsweep
        Traceback (most recent call last):
         ...
        AttributeError: SensorConfig has too many subsweeps ...
        """
        if len(self.subsweeps) > 1:
            raise AttributeError(_TOO_MANY_SUBSWEEPS_ERROR_FORMAT.format("subsweep"))

        return self.subsweeps[0]

    @property
    def num_subsweeps(self) -> int:
        """Get the number of subsweeps"""
        return len(self.subsweeps)

    @property
    def frame_shape(self) -> tuple[int, int]:
        """The shape of the data array produced when measuring with this config"""
        return (
            self.sweeps_per_frame,
            sum(ss.num_points * ss.num_channels for ss in self.subsweeps),
        )

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "subsweeps": [
                    subsweep_config_timeline.migrate(subsweep_dict)
                    for subsweep_dict in dict_repr["subsweeps"]
                ],
            }
        )

    def validate(self) -> None:
        """Performs self-validation and validation of its subsweep configs

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)

    def _collect_validation_results(self) -> list[ValidationResult]:
        validation_results: list[ValidationResult] = []
        if (
            self.inter_frame_idle_state is IdleState.ARMED
            and self.inter_sweep_idle_state is IdleState.READY
        ):
            validation_results.extend(
                [
                    ValidationError(
                        self,
                        "inter_frame_idle_state",
                        "Cannot be ARMED when inter-sweep idle state is READY",
                    ),
                    ValidationError(
                        self,
                        "inter_sweep_idle_state",
                        "Cannot be READY when inter-frame idle state is ARMED",
                    ),
                ]
            )

        if self.sweep_rate is not None and self.sweeps_per_frame <= 1:
            validation_results.extend(
                [
                    ValidationError(self, "sweep_rate", "A set sweep rate requires SPF > 1"),
                    ValidationError(
                        self, "sweeps_per_frame", "Should be > 1 if sweep rate is set"
                    ),
                ]
            )

        if (
            self.frame_rate is not None
            and self.sweep_rate is not None
            and self.frame_rate > (self.sweep_rate / self.sweeps_per_frame)
        ):
            validation_results.extend(
                [
                    ValidationError(
                        self,
                        "frame_rate",
                        f"Too high to measure {self.sweeps_per_frame} sweeps with sweep rate {self.sweep_rate:.2f} Hz. Frame rate can to be at most {(self.sweep_rate / self.sweeps_per_frame):.2f} Hz",
                    ),
                    ValidationError(
                        self,
                        "sweep_rate",
                        f"Too low to measure a {self.sweeps_per_frame}-sweep frame with frame rate {self.frame_rate} Hz. Sweep rate should be at least {self.frame_rate * self.sweeps_per_frame:.2f} Hz",
                    ),
                    ValidationError(
                        self,
                        "sweeps_per_frame",
                        f"Too high. Sweeps per frame should be at most {math.floor(self.sweep_rate / self.frame_rate)}",
                    ),
                ]
            )

        if self.jitter_compensation and len(self.subsweeps) >= self.MAX_NUM_SUBSWEEPS:
            validation_results.append(
                ValidationError(
                    self,
                    "jitter_compensation",
                    f"Requires a free subsweep slot. Use at most "
                    f"{self.MAX_NUM_SUBSWEEPS - 1} subsweeps",
                )
            )

        for subsweep in self.subsweeps:
            validation_results.extend(subsweep._collect_validation_results())
        return validation_results


@attrs.mutable
class _SensorConfig_v2(AttrsMappingTransformsMixin):
    subsweeps: list[SubsweepConfig] = attrs.field(
        validator=[av.deep_iterable(av.instance_of(SubsweepConfig)), av.min_len(1)]
    )
    sweeps_per_frame: int = attrs.field(validator=av.ge(0))
    sweep_rate: float | None = attrs.field(
        converter=ac.optional(float), validator=av.optional(av.gt(0))
    )
    frame_rate: float | None = attrs.field(
        converter=ac.optional(float), validator=av.optional(av.gt(0))
    )
    inter_frame_idle_state: IdleState = attrs.field(converter=IdleState)
    inter_sweep_idle_state: IdleState = attrs.field(converter=IdleState)

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "subsweeps": [
                    subsweep_config_timeline.migrate(subsweep_dict)
                    for subsweep_dict in dict_repr["subsweeps"]
                ],
            }
        )


@attrs.mutable
class _SensorConfig_v1(AttrsMappingTransformsMixin):
    subsweeps: list[SubsweepConfig] = attrs.field(
        validator=[av.deep_iterable(av.instance_of(SubsweepConfig)), av.min_len(1)]
    )
    sweeps_per_frame: int = attrs.field(validator=av.ge(0))
    sweep_rate: float | None = attrs.field(
        converter=ac.optional(float), validator=av.optional(av.gt(0))
    )

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "subsweeps": [
                    subsweep_config_timeline.migrate(subsweep_dict)
                    for subsweep_dict in dict_repr["subsweeps"]
                ],
            }
        )


@attrs.mutable
class _SensorConfig_v0(AttrsMappingTransformsMixin):
    subsweeps: list[SubsweepConfig] = attrs.field(
        validator=[av.deep_iterable(av.instance_of(SubsweepConfig)), av.min_len(1)]
    )

    sweeps_per_frame: int = attrs.field(validator=av.ge(0))

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "subsweeps": [
                    subsweep_config_timeline.migrate(subsweep_dict)
                    for subsweep_dict in dict_repr["subsweeps"]
                ],
            }
        )


sensor_config_timeline = (
    tm.start(_SensorConfig_v0)
    .load(dict, _SensorConfig_v0.from_dict, fail=[TypeError])
    .load(str, _SensorConfig_v0.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(
        _SensorConfig_v1,
        lambda old: _SensorConfig_v1(
            subsweeps=old.subsweeps,
            sweeps_per_frame=old.sweeps_per_frame,
            sweep_rate=None,
        ),
        fail=[],
    )
    .load(dict, _SensorConfig_v1.from_dict, fail=[TypeError])
    .load(str, _SensorConfig_v1.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(
        _SensorConfig_v2,
        lambda old: _SensorConfig_v2(
            subsweeps=old.subsweeps,
            sweeps_per_frame=old.sweeps_per_frame,
            sweep_rate=old.sweep_rate,
            frame_rate=None,
            inter_frame_idle_state=IdleState.ARMED,
            inter_sweep_idle_state=IdleState.ARMED,
        ),
        fail=[],
    )
    .load(dict, _SensorConfig_v2.from_dict, fail=[TypeError])
    .load(str, _SensorConfig_v2.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(
        SensorConfig,
        lambda old: SensorConfig(
            subsweeps=old.subsweeps,
            sweeps_per_frame=old.sweeps_per_frame,
            sweep_rate=old.sweep_rate,
            frame_rate=old.frame_rate,
            inter_frame_idle_state=old.inter_frame_idle_state,
            inter_sweep_idle_state=old.inter_sweep_idle_state,
            jitter_compensation=False,
        ),
        fail=[],
    )
    .load(dict, SensorConfig.from_dict, fail=[TypeError])
    .load(str, SensorConfig.from_json, fail=tm.common_exceptions.FROM_JSON)
)
