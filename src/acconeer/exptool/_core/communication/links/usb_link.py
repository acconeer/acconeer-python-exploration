# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
from __future__ import annotations

from time import sleep, time
from typing import Optional

from acconeer.exptool._pyusb import PyUsbCdc

from .buffered_link import BufferedLink, LinkError


class USBLink(BufferedLink):
    def __init__(
        self, vid: Optional[int] = None, pid: Optional[int] = None, serial: Optional[str] = None
    ) -> None:
        super().__init__()
        self._vid = vid
        self._pid = pid
        self._serial = serial
        self._port: Optional[PyUsbCdc] = None

    def _update_timeout(self) -> None:
        # timeout is manually handled in recv/recv_until
        pass

    def connect(self) -> None:
        if self._vid and self._pid:
            self._port = PyUsbCdc(vid=self._vid, pid=self._pid, serial=self._serial, start=False)
        else:
            msg = "Must have vid and pid for usb device"
            raise LinkError(msg)

        if not self._port.open():
            msg = f"Unable to connect to port (vid={self._vid}, pid={self._pid}"
            raise LinkError(msg)

        self._buf = bytearray()
        self.send_break()

    def send_break(self) -> None:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        self._port.send_break()
        sleep(1.0)
        self._port.reset_input_buffer()

    def recv(self, num_bytes: int) -> bytes:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        t0 = time()
        while len(self._buf) < num_bytes:
            if time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

            try:
                r = bytearray(self._port.read())
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs: bytes) -> bytes:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

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
                r = bytearray(self._port.read())
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data

    def send(self, data: bytes) -> None:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)
        self._port.write(data)

    def disconnect(self) -> None:
        if self._port is not None:
            self._port.close()
            self._port = None
