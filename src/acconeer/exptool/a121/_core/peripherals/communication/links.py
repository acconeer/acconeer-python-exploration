# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a111._clients.links import (  # type: ignore[import]
    ExploreSerialLink,
    SocketLink,
    USBLink,
)
from acconeer.exptool.a121._core.mediators import BufferedLink


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

    def recv(self, num_bytes: int) -> bytes:
        raise self.ERROR

    def send(self, bytes_: bytes) -> None:
        raise self.ERROR

    def disconnect(self) -> None:
        raise self.ERROR

    def recv_until(self, byte_sequence: bytes) -> bytes:
        raise self.ERROR


class AdaptedSocketLink(SocketLink):
    """This subclass only adapts the signature.
    Positional arguments would've executed fine.
    """

    def recv_until(self, byte_sequence: bytes) -> bytes:
        return bytes(super().recv_until(bs=byte_sequence))

    def send(self, bytes_: bytes) -> None:
        super().send(data=bytes_)


class AdaptedSerialLink(ExploreSerialLink):
    """This subclass only adapts the signature.
    Positional arguments would've executed fine.
    """

    def recv_until(self, byte_sequence: bytes) -> bytes:
        return bytes(super().recv_until(bs=byte_sequence))

    def send(self, bytes_: bytes) -> None:
        super().send(data=bytes_)


class AdaptedUSBLink(USBLink):
    """This subclass only adapts the signature.
    Positional arguments would've executed fine.
    """

    def recv_until(self, byte_sequence: bytes) -> bytes:
        return bytes(super().recv_until(bs=byte_sequence))

    def send(self, bytes_: bytes) -> None:
        super().send(data=bytes_)
