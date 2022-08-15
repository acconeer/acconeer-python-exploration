# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import enum
import json
from typing import Any, Dict, Generic, List, Optional, TypeVar

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121._core.utils import EntityJSONEncoder


InputT = TypeVar("InputT", a121.Result, List[Dict[int, a121.Result]])
MetadataT = TypeVar("MetadataT", a121.Metadata, List[Dict[int, a121.Metadata]])
ConfigT = TypeVar("ConfigT", bound="AlgoConfigBase")
ParamEnumT = TypeVar("ParamEnumT", bound="AlgoParamEnum")
ResultT = TypeVar("ResultT")


class GenericProcessorBase(abc.ABC, Generic[InputT, ConfigT, ResultT, MetadataT]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: MetadataT,
        processor_config: ConfigT,
    ) -> None:
        self.sensor_config = sensor_config
        self.metadata: MetadataT = metadata
        self.processor_config = processor_config

    @abc.abstractmethod
    def process(self, result: InputT) -> ResultT:
        ...

    @abc.abstractmethod
    def update_config(self, config: ConfigT) -> None:
        ...


ProcessorBase = GenericProcessorBase[a121.Result, ConfigT, ResultT, a121.Metadata]
ExtendedProcessorBase = GenericProcessorBase[
    List[Dict[int, a121.Result]], ConfigT, ResultT, List[Dict[int, a121.Metadata]]
]


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
