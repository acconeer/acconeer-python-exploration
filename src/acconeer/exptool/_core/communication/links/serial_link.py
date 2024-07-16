# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import logging
import multiprocessing as mp
import platform
import queue
import signal
import threading as th
import traceback
from time import sleep, time
from typing import Optional, Tuple, Union

import serial

from .buffered_link import BufferedLink, LinkError


log = logging.getLogger(__name__)


class BaseSerialLink(BufferedLink):
    def __init__(self, baudrate: int = 115200) -> None:
        super().__init__()
        self._timeout = self.DEFAULT_TIMEOUT
        self._baudrate = baudrate


class SerialLink(BaseSerialLink):
    def __init__(self, port: Optional[str] = None, flowcontrol: bool = False) -> None:
        super().__init__()
        self._port = port
        self._ser: Optional[serial.Serial] = None
        self._flowcontrol = flowcontrol

    def _update_timeout(self) -> None:
        if self._ser is not None:
            self._ser.timeout = self._timeout

    def send_break(self) -> None:
        assert self._ser is not None
        self._ser.send_break()
        sleep(1.0)
        self._ser.flushInput()

    def connect(self) -> None:
        self._ser = serial.Serial()
        self._ser.baudrate = self._baudrate
        self._ser.port = self._port
        self._ser.rtscts = self._flowcontrol
        self._update_timeout()
        self._ser.open()

        if platform.system().lower() == "windows":
            self._ser.set_buffer_size(rx_size=10**6, tx_size=10**6)

    def recv(self, num_bytes: int) -> bytes:
        assert self._ser is not None
        data = bytearray(self._ser.read(num_bytes))

        if len(data) != num_bytes:
            msg = "recv timeout"
            raise LinkError(msg)

        return data

    def recv_until(self, bs: bytes) -> bytes:
        assert self._ser is not None
        data = bytearray(self._ser.read_until(bs))

        if bs not in data:
            msg = "recv timeout"
            raise LinkError(msg)

        return data

    def send(self, data: bytes) -> None:
        assert self._ser is not None
        self._ser.write(data)

    def disconnect(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    @property
    def baudrate(self) -> int:
        return self._baudrate

    @baudrate.setter
    def baudrate(self, new_baudrate: int) -> None:
        self._baudrate = new_baudrate

        if self._ser is not None and self._ser.is_open:
            self._ser.baudrate = new_baudrate


class ExploreSerialLink(SerialLink):
    _SERIAL_READ_PACKET_SIZE = 65536
    _SERIAL_PACKET_TIMEOUT = 0.01
    _SERIAL_WRITE_TIMEOUT = 1.0

    def __init__(self, port: str, flowcontrol: bool = True) -> None:
        super().__init__(port, flowcontrol)
        self._buf = bytearray()

    def _update_timeout(self) -> None:
        pass

    def connect(self) -> None:
        self._ser = serial.Serial(
            timeout=self._SERIAL_PACKET_TIMEOUT,
            write_timeout=self._SERIAL_WRITE_TIMEOUT,
            exclusive=True,
        )
        self._ser.baudrate = self._baudrate
        self._ser.port = self._port
        self._ser.rtscts = self._flowcontrol
        self._ser.open()
        self._buf = bytearray()

        if platform.system().lower() == "windows":
            self._ser.set_buffer_size(rx_size=10**6, tx_size=10**6)

        self.send_break()

    def recv(self, num_bytes: int) -> bytes:
        assert self._ser is not None
        t0 = time()
        while len(self._buf) < num_bytes:
            if time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

            try:
                r = bytearray(self._ser.read(self._SERIAL_READ_PACKET_SIZE))
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs: bytes) -> bytes:
        assert self._ser is not None
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
                r = bytearray(self._ser.read(self._SERIAL_READ_PACKET_SIZE))
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data


class SerialProcessLink(BaseSerialLink):
    def __init__(self, port: Optional[int] = None) -> None:
        super().__init__()
        self._port = port
        self._process: Optional[mp.Process] = None

    def _update_timeout(self) -> None:
        pass

    def connect(self) -> None:
        self._recv_queue: "mp.Queue[bytes]" = mp.Queue()
        self._send_queue: "mp.Queue[Union[Tuple[str, int], bytes]]" = mp.Queue()
        self._flow_event = mp.Event()
        self._error_event = mp.Event()

        args = (
            self._port,
            self._baudrate,
            self._recv_queue,
            self._send_queue,
            self._flow_event,
            self._error_event,
        )

        self._process = mp.Process(
            target=serial_process_program,
            args=args,
            daemon=True,
        )

        if self._process is None:
            msg = "failed to create subprocess"
            raise LinkError(msg)

        self._process.start()

        flow_event_was_set = self._flow_event.wait(self._timeout)

        if flow_event_was_set:
            log.debug("connect - flow event was set")
        else:
            log.debug("connect - flow event was not set (timeout)")
            self.disconnect()
            msg = "failed to connect, timeout"
            raise LinkError(msg)

        if self._error_event.is_set():
            log.debug("connect - error event was set")
            self.disconnect()
            msg = "failed to connect, see traceback from serial process"
            raise LinkError(msg)

        log.debug("connect - successful")

        self._buf = bytearray()

    def recv(self, num_bytes: int) -> bytes:
        self.__empty_queue_into_buf()

        t0 = time()
        while len(self._buf) < num_bytes:
            self.__get_into_buf()

            if time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs: bytes) -> bytes:
        self.__empty_queue_into_buf()

        n = len(bs)
        si = 0
        t0 = time()
        while True:
            buf_size = len(self._buf)
            if buf_size >= n:
                try:
                    i = self._buf.index(bs, si)
                except ValueError:
                    pass
                else:
                    break

                si = buf_size - n + 1

            if time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

            self.__get_into_buf()

        data = self._buf[: i + n]
        self._buf = self._buf[i + n :]
        return data

    def send(self, data: bytes) -> None:
        self._send_queue.put(data)

    def disconnect(self) -> None:
        if self._process is not None:
            if self._process.exitcode is None:
                self._flow_event.clear()
                self._process.join(1)

            if self._process.exitcode is None:
                log.info("forcing disconnect...")
                self._process.terminate()
                self._process.join(1)
                log.info("forced disconnect successful")

            if self._process.exitcode is None:
                msg = "failed to disconnect"
                raise LinkError(msg)

    def __empty_queue_into_buf(self) -> None:
        while True:
            try:
                data = self._recv_queue.get_nowait()
            except queue.Empty:
                break

            self._buf.extend(data)

    def __get_into_buf(self) -> None:
        try:
            data = self._recv_queue.get(timeout=self._timeout)
        except queue.Empty:
            msg = "recv timeout"
            raise LinkError(msg)
        except InterruptedError:
            return  # fixes interrupt issue on Windows

        self._buf.extend(data)

    @property
    def baudrate(self) -> int:
        return self._baudrate

    @baudrate.setter
    def baudrate(self, new_baudrate: int) -> None:
        self._baudrate = new_baudrate

        if self._process is not None and self._process.exitcode is None:
            log.debug("Changing baudrate to {}".format(new_baudrate))
            self._send_queue.put(("baudrate", new_baudrate))


def serial_process_program(
    port: int,
    baud: int,
    recv_q: "mp.Queue[bytes]",
    send_q: "mp.Queue[Union[Tuple[str, int], bytes]]",
    flow_event: th.Event,
    error_event: th.Event,
) -> None:
    log.debug("serial communication process started")
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        _serial_process_program(port, baud, recv_q, send_q, flow_event, error_event)
    except Exception:
        error_event.set()
        flow_event.set()
        sleep(0.1)  # give the main process some time to print log messages
        print("Exception raised in serial process:\n")
        traceback.print_exc()
        print("\n\n")

    recv_q.close()
    send_q.close()


def _serial_process_program(
    port: int,
    baud: int,
    recv_q: "mp.Queue[bytes]",
    send_q: "mp.Queue[Union[Tuple[str, int], bytes]]",
    flow_event: th.Event,
    error_event: th.Event,
) -> None:
    ser = serial.Serial(port=port, baudrate=baud, timeout=0, exclusive=True)
    flow_event.set()
    while flow_event.is_set():
        received = bytearray()
        while True:
            data = bytearray(ser.read(4096))
            if len(data) == 0:
                break
            received.extend(data)
        if len(received) > 0:
            recv_q.put(received)

        sent = False
        while True:
            try:
                x = send_q.get_nowait()
            except queue.Empty:
                break

            if isinstance(x, tuple):
                _, val = x  # assume its a baudrate change
                ser.baudrate = val
            else:
                ser.write(x)
                sent = True

        if not sent:
            sleep(0.0025)

    ser.close()
