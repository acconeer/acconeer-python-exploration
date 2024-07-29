# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import json
import warnings
from typing import Any, Optional, Union

import numpy as np

from acconeer.exptool._core.class_creation.formatting import pretty_dict_line_strs
from acconeer.exptool._core.entities.validation_result import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from acconeer.exptool.a121._core import utils

from .sensor_config import SensorConfig


@utils.no_dynamic_member_creation
class SessionConfig:
    """Session configuration

    The session configuration defines the highest level of configuration available in Exploration
    Tool. It mainly consists of one or several sensor configurations (:class:`SensorConfig`) for
    the server to run. It also sets the update rate for the server, and the data format
    ("extended") returned from the client.

    Mapping from sensor ID to sensor config is done here in the session config. For example, if you
    want to want to use sensor 2, you can do:

    .. code-block:: python

        SessionConfig({2: SensorConfig(start_point=123)})

    The default sensor ID is 1. Going further, you may run multiple sensors at the same time (in
    parallel) like this:

    .. code-block:: python

        SessionConfig(
            {
                2: SensorConfig(start_point=123),
                3: SensorConfig(start_point=456),
            }
        )

    The dictionary shown above forms a *group* of sensor configs. Further extending upon this, you
    may specify multiple groups which are run in sequence, like this:

    .. code-block:: python

        SessionConfig(
            [
                {
                    2: SensorConfig(start_point=123),
                    3: SensorConfig(start_point=456),
                },
                {
                    2: SensorConfig(start_point=789),
                },
            ]
        )

    You may reuse the same sensor across groups. If a sensor is used multiple times, a
    reconfiguration will be done prior to each measurement.

    A session config with multiple sensor configs (in a single group or multiple) is considered
    "extended". This is reflected in the shape of some return types. A SessionConfig with a single
    SensorConfig is not extended, but the return values can be passed as extended with the keyword
    argument ``extended=True``, see below:

    >>> SessionConfig([{1: SensorConfig()}])
    SessionConfig(groups=[{1: ...}], ..., extended=False)

    >>> SessionConfig([{1: SensorConfig(), 2: SensorConfig()}])
    SessionConfig(groups=[{1: ..., 2: ...}], ..., extended=True)

    >>> SessionConfig([{1: SensorConfig()}], extended=True)
    SessionConfig(groups=[{1: ...}], ..., extended=True)

    :param arg: The sensor configuration(s).
    :param extended:
        Forces whether to use the extended format or not. If not given (``= None``), the extended
        format will be used automatically if multiple sensor configs are given.
    :param update_rate:
        The update rate limit on the server. Defaults to None, not limiting the rate.
    :raises ValueError: If the session config must be extended but ``extended=False``.
    """

    def __init__(
        self,
        arg: Optional[
            Union[SensorConfig, dict[int, SensorConfig], list[dict[int, SensorConfig]]]
        ] = None,
        *,
        extended: Optional[bool] = None,
        update_rate: Optional[float] = None,
    ) -> None:
        self.update_rate = update_rate

        if arg is None:
            self._groups = [{1: SensorConfig()}]
        else:
            self._groups = _unsqueeze_groups(arg)
        _validate_groups_structure(self._groups)

        num_entries = sum(len(g) for g in self._groups)
        must_be_extended = num_entries > 1

        if extended is None:
            self._extended = must_be_extended
        else:
            self._extended = extended

        if extended is not None and not extended and must_be_extended:
            msg = "Must be extended since multiple sensor configs are given"
            raise ValueError(msg)

    @property
    def extended(self) -> bool:
        """Whether or not the extended format is used"""

        return self._extended

    @property
    def groups(self) -> list[dict[int, SensorConfig]]:
        """The sensor config groups of this session"""

        return self._groups

    @property
    def update_rate(self) -> Optional[float]:
        """The server update rate limit in Hz

        Must be > 0 or None, where None means unlimited.
        """

        return self._update_rate

    @update_rate.setter
    def update_rate(self, value: Optional[float]) -> None:
        if value is None:
            self._update_rate = None
        else:
            self._update_rate = utils.validate_float(value, min_value=0.0, inclusive=False)

    def _assert_not_extended(self) -> None:
        if self.extended:
            msg = "This operation requires SessionConfig not to be extended."
            raise RuntimeError(msg)

    def _collect_validation_results(self) -> list[ValidationResult]:
        validation_results = []
        for group in self._groups:
            for _, sensor_config in group.items():
                validation_results.extend(sensor_config._collect_validation_results())

        if self.update_rate is not None:
            for group_id, sensor_id, sensor_config in utils.iterate_extended_structure(
                self._groups
            ):
                if sensor_config.frame_rate is not None:
                    validation_results.append(
                        ValidationError(
                            self,
                            "update_rate",
                            "A set update rate is incompatible with a set frame rate of sensor "
                            + f"{sensor_id} in group {group_id}",
                        )
                    )
                    validation_results.append(
                        ValidationError(
                            sensor_config,
                            "frame_rate",
                            "A set frame rate is incompatible with a set update rate",
                        )
                    )

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

    @property
    def sensor_id(self) -> int:
        """Retrieves the sole sensor ID

        :raises RuntimeError: If this session config is extended
        """

        self._assert_not_extended()
        (group,) = self._groups
        (sensor_id,) = group.keys()
        return sensor_id

    @sensor_id.setter
    def sensor_id(self, sensor_id: int) -> None:
        """Sets the sole sensor ID

        :raises RuntimeError: If this session config is extended
        """

        self._assert_not_extended()
        (group,) = self._groups
        (old_sensor_id,) = group.keys()
        group[sensor_id] = group.pop(old_sensor_id)

    @property
    def sensor_config(self) -> SensorConfig:
        """Retrieves the sole sensor config

        :raises RuntimeError: If this session config is extended
        """

        self._assert_not_extended()
        (group,) = self._groups
        (sensor_config,) = group.values()
        return sensor_config

    def __eq__(self, other: Any) -> bool:
        return type(self) == type(other) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            + f"groups={self.groups}, update_rate={self.update_rate}, extended={self.extended}"
            + ")"
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"groups": [], "extended": self.extended}
        for group_dict in self._groups:
            d["groups"].append(
                {
                    sensor_id: sensor_config.to_dict()
                    for sensor_id, sensor_config in group_dict.items()
                }
            )

        d["update_rate"] = self._update_rate
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionConfig:
        d = d.copy()
        d["arg"] = []
        groups_list = d.pop("groups")

        for group_dict in groups_list:
            d["arg"].append(
                {
                    sensor_id: SensorConfig.from_dict(sensor_config_dict)
                    for sensor_id, sensor_config_dict in group_dict.items()
                }
            )

        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=utils.EntityJSONEncoder)

    @classmethod
    def from_json(cls, json_str: str) -> SessionConfig:
        session_config_dict = json.loads(json_str)

        # sensor_ids in groups will be strings.
        groups_list = session_config_dict.pop("groups")
        session_config_dict["groups"] = []
        for group_dict in groups_list:
            session_config_dict["groups"].append(
                {
                    int(str_sensor_id): sensor_config_dict
                    for str_sensor_id, sensor_config_dict in group_dict.items()
                }
            )

        return cls.from_dict(session_config_dict)

    def __str__(self) -> str:
        lines = []

        lines.append(f"{type(self).__name__}:")

        d = self.to_dict()
        del d["groups"]
        lines.extend(pretty_dict_line_strs(d))

        lines.append("  groups:")
        for group_idx, group_dict in enumerate(self.groups):
            lines.append(f"    group {group_idx}:")
            for sensor_id, sensor_config in group_dict.items():
                sc_lines = sensor_config._pretty_str_lines(sensor_id=sensor_id)
                lines.extend(utils.indent_strs(sc_lines, 3))

        return "\n".join(lines)


def _unsqueeze_groups(
    arg: Union[SensorConfig, dict[int, SensorConfig], list[dict[int, SensorConfig]]],
) -> list[dict[int, SensorConfig]]:
    if isinstance(arg, SensorConfig):
        return [{1: arg}]

    if isinstance(arg, dict):
        return [arg]

    if isinstance(arg, list):
        return arg

    raise ValueError


def _validate_groups_structure(groups: list[dict[int, SensorConfig]]) -> None:
    if len(groups) < 1:
        raise ValueError

    for group in groups:
        if len(group) < 1:
            raise ValueError

        for sensor_id, entry in group.items():
            if not isinstance(sensor_id, (int, np.int64, np.int32)):
                msg = f"{type(sensor_id)} not int"
                raise ValueError(msg)

            if not isinstance(entry, SensorConfig):
                raise ValueError
