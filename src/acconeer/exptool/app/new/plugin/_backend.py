from __future__ import annotations

import abc
from typing import Any, Callable, Dict, Tuple


TaskName = str
TaskKwargs = Dict[str, Any]
Task = Tuple[TaskName, TaskKwargs]


class BackendPlugin(abc.ABC):
    @abc.abstractmethod
    def setup(self, *, callback: Callable) -> None:
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
