# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

import abc


class BufferedLink(abc.ABC):
    DEFAULT_TIMEOUT: float = 2.0

    def __init__(self) -> None:
        self._timeout = self.DEFAULT_TIMEOUT

    @property
    def timeout(self) -> float:
        """Return link timout."""
        return self._timeout

    @timeout.setter
    def timeout(self, timeout: float) -> None:
        """Set return link timeout."""
        self._timeout = timeout
        self._update_timeout()

    @abc.abstractmethod
    def _update_timeout(self) -> None:
        """Propagates the newly set timeout (found in self._timeout)"""

    @abc.abstractmethod
    def connect(self) -> None:
        """Establishes a connection."""

    @abc.abstractmethod
    def recv(self, num_bytes: int) -> bytes:
        """Recieves `num_bytes` bytes."""

    @abc.abstractmethod
    def recv_until(self, byte_sequence: bytes) -> bytes:
        """Collects all bytes until `byte_sequence` is encountered,
        returning what was collected
        """

    @abc.abstractmethod
    def send(self, bytes_: bytes) -> None:
        """Sends all `bytes_` over the link."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Tears down the connection."""


class LinkError(RuntimeError):
    pass
