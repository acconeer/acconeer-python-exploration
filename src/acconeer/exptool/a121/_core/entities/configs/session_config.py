from __future__ import annotations

import json
from typing import Any, Optional, Union

from acconeer.exptool.a121._core import utils

from .sensor_config import SensorConfig


class SessionConfig:
    """Configuration of a session.

    A session consists of groups of SensorConfigs.
    Groups are run sequentially while SensorConfigs in a single group
    are run in parallel.

    A SessionConfig with multiple SensorConfigs (in a single group or multiple)
    is considered "extended". Which is reflected in the shape of some return types.

    A SessionConfig with a single SensorConfig is not extended, but the return values can
    be passed as extended with the keyword argument `extended=True`
    """

    _groups: list[dict[int, SensorConfig]]

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
        _validate_groups(self._groups)

        num_entries = sum(len(g) for g in self._groups)
        must_be_extended = num_entries > 1

        if extended is None:
            self._extended = must_be_extended
        else:
            self._extended = extended

        if extended is not None:
            if not extended and must_be_extended:
                raise ValueError

    @property
    def extended(self) -> bool:
        """Extended."""
        return self._extended

    @property
    def update_rate(self) -> Optional[float]:
        """Update rate.

        The update rate in Hz. Must be > 0,
        `update_rate = None` is interpreted as unlimited.
        """
        return self._update_rate

    @update_rate.setter
    def update_rate(self, value: Optional[float]) -> None:
        if value is None:
            self._update_rate = None
        else:
            self._update_rate = utils.validate_float(value, min_value=0.0, inclusive=False)

    def _assert_not_extended(self):
        if self.extended:
            raise RuntimeError("This operation requires SessionConfig not to be extended.")

    @property
    def sensor_id(self) -> int:
        """If not extended, retrieves the `sensor_id`."""
        self._assert_not_extended()
        (group,) = self._groups
        (sensor_id,) = group.keys()
        return sensor_id

    @property
    def sensor_config(self) -> SensorConfig:
        """If not extended, retrieves the `session_config`."""
        self._assert_not_extended()
        (group,) = self._groups
        (sensor_config,) = group.values()
        return sensor_config

    def __eq__(self, other: Any) -> bool:
        return (
            type(self) == type(other)
            and self.extended == other.extended
            and self.update_rate == other.update_rate
            and self._groups == other._groups
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

        if self._update_rate is not None:
            d["update_rate"] = self._update_rate
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SessionConfig:
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
        return json.dumps(self.to_dict())

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


def _validate_groups(groups):
    if len(groups) < 1:
        raise ValueError

    for group in groups:
        if len(group) < 1:
            raise ValueError

        for sensor_id, entry in group.items():
            if not isinstance(sensor_id, int):
                raise ValueError

            if not isinstance(entry, SensorConfig):
                raise ValueError
