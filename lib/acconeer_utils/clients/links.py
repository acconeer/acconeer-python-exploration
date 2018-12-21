from abc import ABCMeta, abstractmethod
import serial
import socket
from time import time, sleep
import multiprocessing as mp
import queue
import signal
import logging
import traceback

from acconeer_utils.clients.base import ClientError


log = logging.getLogger(__name__)


class LinkError(ClientError):
    pass


class BaseLink(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self):
        self._timeout = 3

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


class SocketLink(BaseLink):
    _CHUNK_SIZE = 4096
    _PORT = 6110

    def __init__(self, host=None):
        super().__init__()
        self._host = host
        self._sock = None
        self._buf = None

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self._timeout)

        try:
            self._sock.connect((self._host, self._PORT))
        except OSError as e:
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
    DEFAULT_BAUDRATE = 115200
    MAX_BAUDRATE = 3000000

    def __init__(self):
        super().__init__()
        self.baudrate = self.DEFAULT_BAUDRATE


class SerialLink(BaseSerialLink):
    def __init__(self, port=None):
        super().__init__()
        self._port = port
        self._ser = None

    def connect(self):
        self._ser = serial.Serial()
        self._ser.port = self._port
        self._ser.baudrate = self.baudrate
        self._ser.timeout = self._timeout
        self._ser.open()

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


class SerialProcessLink(BaseSerialLink):
    def __init__(self, port=None):
        super().__init__()
        self._port = port

    def connect(self):
        self._recv_queue = mp.Queue()
        self._send_queue = mp.Queue()
        self._connect_event = mp.Event()

        args = (
            self._port,
            self.baudrate,
            self._recv_queue,
            self._send_queue,
            self._connect_event,
        )

        self._process = mp.Process(
                target=serial_process_program,
                args=args,
                daemon=True,
                )

        self._process.start()
        connected = self._connect_event.wait(1)

        if not connected:
            self.disconnect()
            raise LinkError("failed to connect")

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

        data = self._buf[:i+n]
        self._buf = self._buf[i+n:]
        return data

    def send(self, data):
        self._send_queue.put(data)

    def disconnect(self):
        if self._process.exitcode is None:
            self._connect_event.clear()
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


def serial_process_program(port, baud, recv_q, send_q, connect_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        _serial_process_program(port, baud, recv_q, send_q, connect_event)
    except Exception:
        print("Exception raised in serial process:\n")
        traceback.print_exc()
        print("\n\n")

    recv_q.close()
    send_q.close()
    connect_event.clear()


def _serial_process_program(port, baud, recv_q, send_q, connect_event):
    ser = serial.Serial(port=port, baudrate=baud, timeout=0, exclusive=True)
    connect_event.set()
    while connect_event.is_set():
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
                frame = send_q.get_nowait()
            except queue.Empty:
                break
            ser.write(frame)
            sent = True

        if not sent:
            sleep(0.0025)  # sleep for roughly 2-3 ms depending on OS

    ser.close()
