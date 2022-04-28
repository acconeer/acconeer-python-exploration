from acconeer.exptool.a111._clients.links import (  # type: ignore[import]
    ExploreSerialLink,
    SocketLink,
)


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
