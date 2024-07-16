# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import socket
from time import time
from typing import Optional

from .buffered_link import BufferedLink, LinkError


class SocketLink(BufferedLink):
    _CHUNK_SIZE = 4096
    _PORT = 6110

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        super().__init__()
        self._host = host
        self._sock: Optional[socket.socket] = None
        self._buf: bytearray = bytearray()
        self._port: int = self._PORT if (port is None) else port

    def _update_timeout(self) -> None:
        if self._sock is not None:
            self._sock.settimeout(self._timeout)

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._update_timeout()

        try:
            self._sock.connect((self._host, self._port))
        except OSError as e:
            self._sock.close()
            self._sock = None
            msg = "failed to connect"
            raise LinkError(msg) from e

        self._buf = bytearray()

    def recv(self, num_bytes: int) -> bytes:
        assert self._sock is not None
        while len(self._buf) < num_bytes:
            try:
                r = self._sock.recv(self._CHUNK_SIZE)
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs: bytes) -> bytes:
        assert self._sock is not None
        t0 = time()
        while True:
            try:
                i = self._buf.index(bs)
            except ValueError:
                pass
            else:
                break

            if time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

            try:
                r = self._sock.recv(self._CHUNK_SIZE)
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data

    def send(self, data: bytes) -> None:
        assert self._sock is not None
        self._sock.sendall(data)

    def disconnect(self) -> None:
        if self._sock is not None:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
            self._sock = None
        self._buf = bytearray()
