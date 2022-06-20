from __future__ import annotations

import abc
import enum
import json
from typing import Any, Generic, Optional, TypeVar

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121._core.utils import EntityJSONEncoder


ConfigT = TypeVar("ConfigT", bound="AlgoConfigBase")
ParamEnumT = TypeVar("ParamEnumT", bound="AlgoParamEnum")
ResultT = TypeVar("ResultT")


# TODO: Here we assume that the processor handles a single config entry, but that assumption
# cannot be made in general. Maybe we need different variants?


class ProcessorBase(abc.ABC, Generic[ConfigT, ResultT]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ConfigT,
    ) -> None:
        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config

    @abc.abstractmethod
    def process(self, result: a121.Result) -> ResultT:
        ...

    @abc.abstractmethod
    def update_config(self, config: ConfigT) -> None:
        ...


class AlgoConfigBase:
    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls: type[ConfigT], d: dict) -> ConfigT:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=EntityJSONEncoder)

    @classmethod
    def from_json(cls: type[ConfigT], json_str: str) -> ConfigT:
        return cls.from_dict(json.loads(json_str))


class AlgoParamEnum(enum.Enum):
    # TODO: Share with config_enums.py (?)

    @classmethod
    def _missing_(cls: type[ParamEnumT], value: object) -> Optional[ParamEnumT]:
        for member in cls:
            if member.name == value:
                return member

        return None
