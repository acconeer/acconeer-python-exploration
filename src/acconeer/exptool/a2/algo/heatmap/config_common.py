# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import abc
import functools
import operator
import typing as t
import warnings

import attrs
import attrs.validators as av
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a2
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)


def to_tuple(v: t.Any) -> tuple[float, float]:
    return tuple(v)


_HeatmapConfigT = t.TypeVar("_HeatmapConfigT", bound="HeatmapConfigCommon")


@attrs.mutable
class HeatmapConfigCommon(AttrsMappingTransformsMixin, abc.ABC):
    antenna_array: a2.AntennaArray = attrs.field(converter=a2.AntennaArray)
    """The antenna layout the data is coming from"""

    az_angle_range: tuple[float, float] = attrs.field(
        validator=[av.min_len(2), av.max_len(2)],
        converter=to_tuple,
    )
    """Min and max az angle"""

    el_angle_range: tuple[float, float] = attrs.field(
        validator=[av.min_len(2), av.max_len(2)],
        converter=to_tuple,
    )
    """Min and max el angle"""

    num_az_angles: int = attrs.field(validator=av.gt(0))
    """The number of angles to divide the az range into"""

    num_el_angles: int = attrs.field(validator=av.gt(0))
    """The number of angles to divide the el range into"""

    def _collect_validation_results(self, config: a2.SessionConfig) -> list[ValidationResult]:
        antenna_array_tx_mask = functools.reduce(
            operator.or_,
            (1 << tx_idx for tx_idx in self.antenna_array.txs),
        )
        validation_errors: list[ValidationResult] = []

        # Only the Tx mask check needs the subsweep, so the angle ranges below are
        # still checked for a config the processor cannot take
        sole_subsweep = (
            config.sensor_config.subsweep if config.sensor_config.num_subsweeps == 1 else None
        )

        if sole_subsweep is None:
            validation_errors.append(
                ValidationError(
                    config.sensor_config,
                    "subsweeps",
                    "Heatmap processing takes exactly one subsweep",
                )
            )
        elif bad_bits := sole_subsweep.tx_antenna_mask & ~antenna_array_tx_mask:
            validation_errors.append(
                ValidationError(
                    sole_subsweep,
                    "tx_antenna_mask",
                    f"Tx mask is incompatible with current antenna array (bad bits: {bin(bad_bits)})",
                )
            )
            validation_errors.append(
                ValidationError(
                    self,
                    "antenna_array",
                    f"Antenna array is incompatible with current Tx mask (bad bits: {bin(bad_bits)})",
                )
            )
        if self.az_angle_range[0] > self.az_angle_range[1]:
            validation_errors.append(
                ValidationError(
                    self,
                    "az_angle_range",
                    "Start of range cannot be higher than end of range.",
                )
            )
        if self.el_angle_range[0] > self.el_angle_range[1]:
            validation_errors.append(
                ValidationError(
                    self,
                    "el_angle_range",
                    "Start of range cannot be higher than end of range.",
                )
            )
        return validation_errors

    def validate(self, config: a2.SessionConfig) -> None:
        """Performs self-validation and validation of its sensor configs

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results(config):
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)

    def to_dict(self) -> dict[str, t.Any]:
        return attrs.asdict(self, recurse=False)

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "antenna_array": a2.AntennaArray(dict_repr["antenna_array"]),
            }
        )

    @classmethod
    @abc.abstractmethod
    def default(cls) -> te.Self:
        pass

    @staticmethod
    def _get_angles(num: int, angle_range: tuple[float, float]) -> npt.NDArray[np.float64]:
        if num == 1:  # Default behavior of what to do with a single depth
            midpoint = (angle_range[0] + angle_range[1]) / 2.0
            angles = np.array([midpoint])
        else:
            angles = np.linspace(
                start=angle_range[0], stop=angle_range[1], num=num, endpoint=True, dtype=np.float64
            )
        return angles

    @property
    def az_angles(self) -> npt.NDArray[np.float64]:
        """Get the az angles defined by this config."""
        return self._get_angles(self.num_az_angles, self.az_angle_range)

    @property
    def az_start(self) -> float:
        """Return the smallest az angle in az_angles"""
        return float(self.az_angles[0])

    @property
    def az_end(self) -> float:
        """Return the largest az angle in az_angles"""
        return float(self.az_angles[-1])

    @property
    def az_span(self) -> float:
        """Return the difference of largest and smallest az angle in az_angles"""
        return float(max(self.az_angles) - min(self.az_angles))

    @property
    def el_angles(self) -> npt.NDArray[np.float64]:
        """Get the el angles defined by this config."""
        return self._get_angles(self.num_el_angles, self.el_angle_range)

    @property
    def el_start(self) -> float:
        """Return the smallest el angle in el_angles"""
        return float(self.el_angles[0])

    @property
    def el_end(self) -> float:
        """Return the largest el angle in el_angles"""
        return float(self.el_angles[-1])

    @property
    def el_span(self) -> float:
        """Return the difference of largest and smallest el angles in el_angles"""
        return float(max(self.el_angles) - min(self.el_angles))


@attrs.mutable
class HeatmapAndSessionConfigCommon(abc.ABC, t.Generic[_HeatmapConfigT]):
    """A heatmap config together with the session config it is meant for

    Both are optional because the editors hand over whatever they hold, which is
    None while a field is being edited.
    """

    heatmap_config: _HeatmapConfigT | None
    session_config: a2.SessionConfig | None

    @classmethod
    @abc.abstractmethod
    def default(cls) -> te.Self:
        pass
