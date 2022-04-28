from __future__ import annotations

import json
from typing import Any, Optional, Union

from ._sensor_config import SensorConfig


class SessionConfig:
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
        return self._extended

    @property
    def update_rate(self) -> Optional[float]:
        return self._update_rate

    @update_rate.setter
    def update_rate(self, value: Optional[float]) -> None:
        if value is not None:
            if value < 0:
                raise ValueError("update_rate must be > 0")

        self._update_rate = value

    def _assert_not_extended(self):
        if self.extended:
            raise RuntimeError("This operation requires SessionConfig not to be extended.")

    @property
    def sensor_id(self) -> int:
        self._assert_not_extended()
        (group,) = self._groups
        (sensor_id,) = group.keys()
        return sensor_id

    @property
    def sensor_config(self) -> SensorConfig:
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
