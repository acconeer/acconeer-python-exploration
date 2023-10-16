# Copyright (c) Acconeer AB, 2023
# All rights reserved

from .buffered_link import BufferedLink


class NullLinkError(RuntimeError):
    pass


class NullLink(BufferedLink):
    ERROR = NullLinkError("Link is undetermined.")
    """Link null object.

    :raises: ``RuntimeError`` if any of its methods is called.
    """

    def connect(self) -> None:
        raise self.ERROR

    @property
    def timeout(self) -> float:
        raise self.ERROR

    @timeout.setter
    def timeout(self, timeout: float) -> None:
        raise self.ERROR

    def _update_timeout(self) -> None:
        pass

    def recv(self, num_bytes: int) -> bytes:
        raise self.ERROR

    def send(self, bytes_: bytes) -> None:
        raise self.ERROR

    def disconnect(self) -> None:
        raise self.ERROR

    def recv_until(self, byte_sequence: bytes) -> bytes:
        raise self.ERROR
