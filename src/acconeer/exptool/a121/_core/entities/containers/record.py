from __future__ import annotations

import abc
from typing import Any, Iterable

from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.entities.configs import SessionConfig

from .client_info import ClientInfo
from .metadata import Metadata
from .result import Result
from .server_info import ServerInfo
from .stacked_results import StackedResults


class Record(abc.ABC):
    @property
    @abc.abstractmethod
    def client_info(self) -> ClientInfo:
        ...

    @property
    @abc.abstractmethod
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        ...

    @property
    def metadata(self) -> Metadata:
        return utils.unextend(self.extended_metadata)

    @property
    @abc.abstractmethod
    def extended_results(self) -> Iterable[list[dict[int, Result]]]:
        ...

    @property
    def results(self) -> Iterable[Result]:
        for extended_result in self.extended_results:
            yield utils.unextend(extended_result)

    @property
    @abc.abstractmethod
    def extended_stacked_results(self) -> list[dict[int, StackedResults]]:
        ...

    @property
    def stacked_results(self) -> StackedResults:
        return utils.unextend(self.extended_stacked_results)

    @property
    @abc.abstractmethod
    def lib_version(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def num_frames(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def server_info(self) -> ServerInfo:
        ...

    @property
    @abc.abstractmethod
    def session_config(self) -> SessionConfig:
        ...

    @property
    @abc.abstractmethod
    def sensor_id(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def timestamp(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def uuid(self) -> str:
        ...


class PersistentRecord(Record):
    @abc.abstractmethod
    def close(self) -> None:
        pass

    def __enter__(self) -> Record:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
