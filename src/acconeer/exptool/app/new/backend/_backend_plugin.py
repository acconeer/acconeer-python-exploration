from __future__ import annotations

import abc
from typing import Any, Callable

from ._message import Message
from ._types import Task


class BackendPlugin(abc.ABC):
    def __init__(self, callback: Callable[[Message], None], key: str) -> None:
        self.callback = callback
        self.key = key

    @abc.abstractmethod
    def idle(self) -> bool:
        pass

    @abc.abstractmethod
    def attach_client(self, *, client: Any) -> None:
        pass

    @abc.abstractmethod
    def detach_client(self) -> None:
        pass

    @abc.abstractmethod
    def execute_task(self, *, task: Task) -> None:
        pass

    @abc.abstractmethod
    def teardown(self) -> None:
        pass
