from __future__ import annotations

import abc
from typing import Any, Iterable

from acconeer.exptool.a121._entities.configs import SessionConfig

from ._client_info import ClientInfo
from ._metadata import Metadata
from ._result import Result
from ._server_info import ServerInfo


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
    @abc.abstractmethod
    def extended_results(self) -> Iterable[list[dict[int, Result]]]:
        ...

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
    def timestamp(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def uuid(self) -> str:
        ...

    @property
    def metadata(self) -> Metadata:
        raise NotImplementedError


class PersistentRecord(Record):
    @abc.abstractmethod
    def close(self) -> None:
        pass

    def __enter__(self) -> Record:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
