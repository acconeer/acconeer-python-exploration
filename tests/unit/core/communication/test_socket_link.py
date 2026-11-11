# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import socket
import struct
import typing as t

import pytest

from acconeer.exptool._core.communication.links import LinkError, SocketLink


@pytest.fixture
def server() -> t.Iterator[socket.socket]:
    with socket.create_server(("127.0.0.1", 0)) as s:
        yield s


def _reset_by_server(server: socket.socket) -> None:
    conn, _ = server.accept()
    # Closing with a zero linger time resets the connection, as when the
    # device is unplugged or the server dies, instead of shutting it down
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    conn.close()


@pytest.mark.parametrize(
    "receive",
    [lambda link: link.recv(1), lambda link: link.recv_until(b"\n")],
    ids=["recv", "recv_until"],
)
def test_lost_connection_says_why(
    server: socket.socket, receive: t.Callable[[SocketLink], bytes]
) -> None:
    link = SocketLink(host="127.0.0.1", port=server.getsockname()[1])
    link.connect()
    _reset_by_server(server)

    with pytest.raises(LinkError) as excinfo:
        receive(link)

    assert str(excinfo.value) != ""
