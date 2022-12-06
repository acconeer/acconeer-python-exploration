# Copyright (c) Acconeer AB, 2022
# All rights reserved

import logging
import multiprocessing as mp
import platform
import queue
import signal
import socket
import traceback
from abc import ABCMeta, abstractmethod
from time import sleep, time

import serial

from acconeer.exptool._pyusb.pyusbcomm import PyUsbCdc
from acconeer.exptool.a111._clients.base import ClientError


try:
    from acconeer.exptool._winusbcdc.usb_cdc import ComPort
except ImportError:
    ComPort = None

log = logging.getLogger(__name__)


class LinkError(ClientError):
    pass


class BaseLink(metaclass=ABCMeta):
    DEFAULT_TIMEOUT = 2

    @abstractmethod
    def __init__(self):
        self._timeout = self.DEFAULT_TIMEOUT

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def recv(self, num_bytes):
        pass

    @abstractmethod
    def recv_until(self, bs):
        pass

    @abstractmethod
    def send(self, data):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, val):
        self._timeout = val
        self._update_timeout()

    def _update_timeout(self):
        pass


class SocketLink(BaseLink):
    _CHUNK_SIZE = 4096
    _PORT = 6110

    def __init__(self, host=None):
        super().__init__()
        self._host = host
        self._sock = None
        self._buf = None

    def _update_timeout(self):
        if self._sock is not None:
            self._sock.settimeout(self._timeout)

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._update_timeout()

        try:
            self._sock.connect((self._host, self._PORT))
        except OSError as e:
            self._sock.close()
            self._sock = None
            raise LinkError("failed to connect") from e

        self._buf = bytearray()

    def recv(self, num_bytes):
        while len(self._buf) < num_bytes:
            try:
                r = self._sock.recv(self._CHUNK_SIZE)
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs):
        t0 = time()
        while True:
            try:
                i = self._buf.index(bs)
            except ValueError:
                pass
            else:
                break

            if time() - t0 > self._timeout:
                raise LinkError("recv timeout")

            try:
                r = self._sock.recv(self._CHUNK_SIZE)
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data

    def send(self, data):
        self._sock.sendall(data)

    def disconnect(self):
        self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        self._sock = None
        self._buf = None


class BaseSerialLink(BaseLink):
    def __init__(self, baudrate=115200):
        super().__init__()
        self._timeout = self.DEFAULT_TIMEOUT
        self._baudrate = baudrate


class SerialLink(BaseSerialLink):
    def __init__(self, port=None, flowcontrol=False):
        super().__init__()
        self._port = port
        self._ser = None
        self._flowcontrol = flowcontrol

    def _update_timeout(self):
        if self._ser is not None:
            self._ser.timeout = self._timeout

    def send_break(self):
        self._ser.send_break()
        sleep(0.5)
        self._ser.flushInput()

    def connect(self):
        self._ser = serial.Serial()
        self._ser.baudrate = self._baudrate
        self._ser.port = self._port
        self._ser.rtscts = self._flowcontrol
        self._update_timeout()
        self._ser.open()

        if platform.system().lower() == "windows":
            self._ser.set_buffer_size(rx_size=10**6, tx_size=10**6)

    def recv(self, num_bytes):
        data = bytearray(self._ser.read(num_bytes))

        if not len(data) == num_bytes:
            raise LinkError("recv timeout")

        return data

    def recv_until(self, bs):
        data = bytearray(self._ser.read_until(bs))

        if bs not in data:
            raise LinkError("recv timeout")

        return data

    def send(self, data):
        self._ser.write(data)

    def disconnect(self):
        self._ser.close()
        self._ser = None

    @property
    def baudrate(self):
        return self._baudrate

    @baudrate.setter
    def baudrate(self, new_baudrate):
        self._baudrate = new_baudrate

        if self._ser is not None and self._ser.is_open:
            self._ser.baudrate = new_baudrate


class ExploreSerialLink(SerialLink):
    _SERIAL_READ_PACKET_SIZE = 65536
    _SERIAL_PACKET_TIMEOUT = 0.01
    _SERIAL_WRITE_TIMEOUT = 1.0

    def __init__(self, port, flowcontrol=True):
        super().__init__(port, flowcontrol)
        self._buf = None

    def _update_timeout(self):
        pass

    def connect(self):
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

    def recv(self, num_bytes):
        t0 = time()
        while len(self._buf) < num_bytes:
            if time() - t0 > self._timeout:
                raise LinkError("recv timeout")

            try:
                r = bytearray(self._ser.read(self._SERIAL_READ_PACKET_SIZE))
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs):
        t0 = time()
        while True:
            try:
                i = self._buf.index(bs)
            except ValueError:
                pass
            else:
                break

            if time() - t0 > self._timeout:
                raise LinkError("recv timeout")

            try:
                r = bytearray(self._ser.read(self._SERIAL_READ_PACKET_SIZE))
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data


class USBLink(BaseLink):
    def __init__(self, vid=None, pid=None, serial=None):
        super().__init__()
        self._vid = vid
        self._pid = pid
        self._serial = serial

    def _update_timeout(self):
        pass

    def connect(self):
        # First try 'ComPort', will be set if platorm == windows
        port_type = ComPort
        if ComPort is None:
            # Fallback to  'PyUsbCdc', will be used if platform != windows
            port_type = PyUsbCdc

        if self._vid and self._pid:
            self._port = port_type(vid=self._vid, pid=self._pid, serial=self._serial, start=False)
        else:
            raise LinkError("Must have vid and pid for usb device")

        if not self._port.open():
            raise LinkError(f"Unable to connect to port (vid={self._vid}, pid={self._pid}")

        self._buf = bytearray()
        self.send_break()

    def send_break(self):
        self._port.send_break()
        sleep(0.5)
        self._port.reset_input_buffer()

    def recv(self, num_bytes):
        t0 = time()
        while len(self._buf) < num_bytes:
            if time() - t0 > self._timeout:
                raise LinkError("recv timeout")

            try:
                r = bytearray(self._port.read())
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs):
        t0 = time()
        while True:
            try:
                i = self._buf.index(bs)
            except ValueError:
                pass
            else:
                break

            if time() - t0 > self._timeout:
                raise LinkError("recv timeout")

            try:
                r = bytearray(self._port.read())
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data

    def send(self, data):
        self._port.write(data)

    def disconnect(self):
        self._port.close()
        self._port = None


class SerialProcessLink(BaseSerialLink):
    def __init__(self, port=None):
        super().__init__()
        self._port = port
        self._process = None

    def connect(self):
        self._recv_queue = mp.Queue()
        self._send_queue = mp.Queue()
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

        self._process.start()

        flow_event_was_set = self._flow_event.wait(self._timeout)

        if flow_event_was_set:
            log.debug("connect - flow event was set")
        else:
            log.debug("connect - flow event was not set (timeout)")
            self.disconnect()
            raise LinkError("failed to connect, timeout")

        if self._error_event.is_set():
            log.debug("connect - error event was set")
            self.disconnect()
            raise LinkError("failed to connect, see traceback from serial process")

        log.debug("connect - successful")

        self._buf = bytearray()

    def recv(self, num_bytes):
        self.__empty_queue_into_buf()

        t0 = time()
        while len(self._buf) < num_bytes:
            self.__get_into_buf()

            if time() - t0 > self._timeout:
                raise LinkError("recv timeout")

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs):
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
                raise LinkError("recv timeout")

            self.__get_into_buf()

        data = self._buf[: i + n]
        self._buf = self._buf[i + n :]
        return data

    def send(self, data):
        self._send_queue.put(data)

    def disconnect(self):
        if self._process.exitcode is None:
            self._flow_event.clear()
            self._process.join(1)

        if self._process.exitcode is None:
            log.info("forcing disconnect...")
            self._process.terminate()
            self._process.join(1)
            log.info("forced disconnect successful")

        if self._process.exitcode is None:
            raise LinkError("failed to disconnect")

    def __empty_queue_into_buf(self):
        while True:
            try:
                data = self._recv_queue.get_nowait()
            except queue.Empty:
                break

            self._buf.extend(data)

    def __get_into_buf(self):
        try:
            data = self._recv_queue.get(timeout=self._timeout)
        except queue.Empty:
            raise LinkError("recv timeout")
        except InterruptedError:
            return  # fixes interrupt issue on Windows

        self._buf.extend(data)

    @property
    def baudrate(self):
        return self._baudrate

    @baudrate.setter
    def baudrate(self, new_baudrate):
        self._baudrate = new_baudrate

        if self._process is not None and self._process.exitcode is None:
            log.debug("Changing baudrate to {}".format(new_baudrate))
            self._send_queue.put(("baudrate", new_baudrate))


def serial_process_program(port, baud, recv_q, send_q, flow_event, error_event):
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


def _serial_process_program(port, baud, recv_q, send_q, flow_event, error_event):
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
