from __future__ import annotations

from typing import Optional, Union

from ._sensor_config import SensorConfig


class SessionConfig:
    def __init__(
        self,
        arg: Union[SensorConfig, dict[int, SensorConfig], list[dict[int, SensorConfig]]],
        *,
        extended: Optional[bool] = None,
        update_rate: Optional[float] = None,
    ) -> None:
        self.update_rate = update_rate

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


def _unsqueeze_groups(arg):
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
