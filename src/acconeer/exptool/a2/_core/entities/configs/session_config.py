# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import typing as t
import warnings

import attrs
import attrs.validators as av
import typing_extensions as te
from attributes_doc import attributes_doc

from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)

from .sensor_config import SensorConfig, sensor_config_timeline


MIN_UPDATE_RATE = 1.157e-5


@attributes_doc
@attrs.mutable
class SessionConfig(AttrsMappingTransformsMixin):
    sensor_configs: list[SensorConfig] = attrs.field(
        validator=[av.deep_iterable(av.instance_of(SensorConfig)), av.min_len(1)]
    )
    """The list of sensor configs"""

    update_rate: t.Optional[float] = attrs.field(validator=av.optional(av.gt(MIN_UPDATE_RATE)))
    """
    The update rate of the server.

    A measurement of every sensor config in ``sensor_configs`` is made in one update period.
    """

    @classmethod
    def default(cls) -> SessionConfig:
        """Creates a default SessionConfig

        Example:

        >>> SessionConfig.default()
        SessionConfig(sensor_configs=[SensorConfig(...)], update_rate=None)
        """
        return cls([SensorConfig.default()], update_rate=None)

    @property
    def sensor_config(self) -> SensorConfig:
        """Return the sole sensor config.

        :raises AttributeError: if `len(sensor_configs) > 1`
        """
        num_sensor_configs = len(self.sensor_configs)
        if num_sensor_configs > 1:
            raise AttributeError(
                'Cannot use accessor "sensor_config" when there are '
                + f"{num_sensor_configs} sensor configs. "
                + "There needs to be exactly one sensor config."
            )

        return self.sensor_configs[0]

    def _collect_validation_results(self) -> list[ValidationResult]:
        validation_results: list[ValidationResult] = []

        if len(self.sensor_configs) > 1:
            for sc in self.sensor_configs:
                if sc.frame_rate is None:
                    continue
                validation_results.append(
                    ValidationError(
                        sc, "frame_rate", "Cannot have a set frame rate with multiple groups."
                    )
                )

        if self.update_rate is not None:
            for sc in self.sensor_configs:
                if sc.frame_rate is None:
                    continue

                validation_results.extend(
                    [
                        ValidationError(
                            self,
                            "update_rate",
                            "A set update rate cannot be combined with a set frame rate",
                        ),
                        ValidationError(
                            sc,
                            "frame_rate",
                            "A set frame rate cannot be combined with a set update rate",
                        ),
                    ]
                )

        for sensor_config in self.sensor_configs:
            validation_results.extend(sensor_config._collect_validation_results())

        return validation_results

    def validate(self) -> None:
        """Performs self-validation and validation of its sensor configs

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except ValidationWarning as vw:
                warnings.warn(vw.message)

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            sensor_configs=[
                sensor_config_timeline.migrate(sensor_config_dict)
                for sensor_config_dict in dict_repr["sensor_configs"]
            ],
            update_rate=dict_repr["update_rate"],
        )
