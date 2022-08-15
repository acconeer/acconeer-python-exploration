# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
from typing import Any, Callable, Generic, Optional, TypeVar

from ._message import BackendPluginStateMessage, Message, StatusMessage


StateT = TypeVar("StateT")


class BackendPlugin(abc.ABC, Generic[StateT]):
    shared_state: StateT

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
    def teardown(self) -> None:
        pass

    def broadcast(self) -> None:
        self.callback(BackendPluginStateMessage(state=self.shared_state))

    def send_status_message(self, message: Optional[str]) -> None:
        self.callback(StatusMessage(status=message))
