# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import enum
import json
import warnings
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121._core.utils import EntityJSONEncoder


AlgoBaseT = TypeVar("AlgoBaseT", bound="AlgoBase")
InputT = TypeVar("InputT", a121.Result, List[Dict[int, a121.Result]])
MetadataT = TypeVar("MetadataT", a121.Metadata, List[Dict[int, a121.Metadata]])
ConfigT = TypeVar("ConfigT", bound="AlgoConfigBase")
ProcessorConfigT = TypeVar("ProcessorConfigT", bound="AlgoProcessorConfigBase")
ParamEnumT = TypeVar("ParamEnumT", bound="AlgoParamEnum")
ResultT = TypeVar("ResultT")


class GenericProcessorBase(abc.ABC, Generic[InputT, ProcessorConfigT, ResultT, MetadataT]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: MetadataT,
        processor_config: ProcessorConfigT,
    ) -> None:
        self.sensor_config = sensor_config
        self.metadata: MetadataT = metadata
        self.processor_config = processor_config

    @abc.abstractmethod
    def process(self, result: InputT) -> ResultT:
        ...

    @abc.abstractmethod
    def update_config(self, config: ProcessorConfigT) -> None:
        ...


ProcessorBase = GenericProcessorBase[a121.Result, ProcessorConfigT, ResultT, a121.Metadata]
ExtendedProcessorBase = GenericProcessorBase[
    List[Dict[int, a121.Result]], ProcessorConfigT, ResultT, List[Dict[int, a121.Metadata]]
]


class AlgoBase:
    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls: type[AlgoBaseT], d: dict[str, Any]) -> AlgoBaseT:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=EntityJSONEncoder)

    @classmethod
    def from_json(cls: type[AlgoBaseT], json_str: str) -> AlgoBaseT:
        return cls.from_dict(json.loads(json_str))


class AlgoConfigBase(AlgoBase):
    def validate(self) -> None:
        """Performs self-validation

        :raises ValidationError: If anything is invalid.
        """
        for validation_result in self._collect_validation_results():
            try:
                raise validation_result
            except a121.ValidationWarning as vw:
                warnings.warn(vw.message)

    @abc.abstractmethod
    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        pass


class AlgoProcessorConfigBase(AlgoBase):
    def validate(self, config: Union[a121.SensorConfig, a121.SessionConfig]) -> None:
        """Performs self-validation and validation of its session config

        :raises ValidationError: If anything is invalid.
        """
        if isinstance(config, a121.SensorConfig):
            config = a121.SessionConfig(config)

        for validation_result in self._collect_validation_results(config):
            try:
                raise validation_result
            except a121.ValidationWarning as vw:
                warnings.warn(vw.message)

    @abc.abstractmethod
    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        pass


class AlgoParamEnum(enum.Enum):
    # TODO: Share with config_enums.py (?)

    @classmethod
    def _missing_(cls: type[ParamEnumT], value: object) -> Optional[ParamEnumT]:
        for member in cls:
            if member.name == value:
                return member

        return None
