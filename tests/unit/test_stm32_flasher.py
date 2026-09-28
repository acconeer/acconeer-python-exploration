# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import functools
import operator

import pytest

from acconeer.exptool.flash._stm32uart import _stm32flasher
from acconeer.exptool.flash._stm32uart._stm32flasher import (
    Stm32FlashException,
    Stm32FlashProtocol,
)


class _FakeUart:
    def __init__(self, reply: bytes = b"") -> None:
        self.reply = reply
        self.written: list[bytes] = []

    def read(self, length: int) -> bytes:
        return self.reply

    def write(self, data: bytes) -> None:
        self.written.append(data)


@pytest.fixture
def uart(monkeypatch: pytest.MonkeyPatch) -> _FakeUart:
    uart = _FakeUart(reply=bytes([Stm32FlashProtocol.ACK]))
    monkeypatch.setattr(_stm32flasher, "UartComm", lambda port: uart)
    return uart


def test_short_reply_raises(uart: _FakeUart) -> None:
    protocol = Stm32FlashProtocol("port")

    with pytest.raises(Stm32FlashException):
        protocol._read_bytes(length=2)


@pytest.mark.parametrize(
    ("chunk", "padded"),
    [
        (b"\x01", b"\x01\xff\xff\xff"),
        (b"\x01\x02\x03", b"\x01\x02\x03\xff"),
        (b"\x01\x02\x03\x04", b"\x01\x02\x03\x04"),
        (b"\x01\x02\x03\x04\x05", b"\x01\x02\x03\x04\x05\xff\xff\xff"),
    ],
)
def test_chunk_is_padded_to_a_multiple_of_four_bytes(
    uart: _FakeUart, chunk: bytes, padded: bytes
) -> None:
    protocol = Stm32FlashProtocol("port")

    protocol._write_memory(0x08000000, bytearray(chunk))

    frame = bytes([len(padded) - 1]) + padded
    assert uart.written[-1] == frame + bytes([functools.reduce(operator.xor, frame)])


def test_oversized_chunk_raises(uart: _FakeUart) -> None:
    protocol = Stm32FlashProtocol("port")

    with pytest.raises(Stm32FlashException):
        protocol._write_memory(0x08000000, bytearray(257))

    assert uart.written == []
