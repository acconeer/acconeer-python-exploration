# Copyright (c) Acconeer AB, 2022
# All rights reserved

from typing_extensions import Protocol


class Link(Protocol):
    def connect(self) -> None:
        """Establishes a connection."""
        ...

    @property
    def timeout(self) -> float:
        """Return link timout."""
        ...

    @timeout.setter
    def timeout(self, timeout: float) -> None:
        """Set return link timeout."""
        ...

    def recv(self, num_bytes: int) -> bytes:
        """Recieves `num_bytes` bytes."""
        ...

    def send(self, bytes_: bytes) -> None:
        """Sends all `bytes_` over the link."""
        ...

    def disconnect(self) -> None:
        """Tears down the connection."""
        ...


class BufferedLink(Link, Protocol):
    def recv_until(self, byte_sequence: bytes) -> bytes:
        """Collects all bytes until `byte_sequence` is encountered,
        returning what was collected
        """
        ...
