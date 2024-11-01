# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import abc
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generic, Iterator, Optional, TypeVar

import h5py

from acconeer.exptool.app.new import PluginGeneration
from acconeer.exptool.app.new.storage import get_config_dir

from ._message import (
    BackendPluginStateMessage,
    Message,
    StatusFileAccessMessage,
    StatusMessage,
    TimingMessage,
)
from ._tasks import is_task


StateT = TypeVar("StateT")


class BackendPlugin(abc.ABC, Generic[StateT]):
    shared_state: StateT

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        self.callback = callback
        self.key = key
        self.generation = generation

    @contextmanager
    def h5_cache_file(self, write: bool = False) -> Iterator[h5py.File]:
        file_path = (get_config_dir() / "plugin" / self.generation.value / self.key).with_suffix(
            ".h5"
        )

        if write:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        file_mode = "w" if write else "r"
        h5_file = h5py.File(file_path, file_mode)
        yield h5_file
        h5_file.close()

    @contextmanager
    def report_timing(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        yield
        end = time.perf_counter()
        self.callback(TimingMessage(name=name, start=start, end=end))

    @is_task
    @abc.abstractmethod
    def load_from_cache(self) -> None:
        pass

    @is_task
    @abc.abstractmethod
    def load_from_file(
        self,
        *,
        path: Path,
        config_override: Optional[Any] = None,
        context_override: Optional[Any] = None,
    ) -> None:
        pass

    @is_task
    @abc.abstractmethod
    def set_preset(self, preset_id: int) -> None:
        pass

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
    def teardown(self) -> None:
        pass

    def broadcast(self) -> None:
        self.callback(BackendPluginStateMessage(state=self.shared_state))

    def send_status_file_access_message(self, file_path: str, opened: bool) -> None:
        self.callback(StatusFileAccessMessage(file_path=file_path, opened=opened))

    def send_status_message(self, message: Optional[str]) -> None:
        self.callback(StatusMessage(status=message))
