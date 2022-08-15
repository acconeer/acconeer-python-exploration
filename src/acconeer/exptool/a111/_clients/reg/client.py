# Copyright (c) Acconeer AB, 2022
# All rights reserved

import abc
import logging
import multiprocessing as mp
import platform
import queue
import signal
import sys
import traceback
from collections import namedtuple
from time import sleep, time

import numpy as np

from acconeer.exptool import libft4222
from acconeer.exptool.a111._clients import links
from acconeer.exptool.a111._clients.base import (
    BaseClient,
    ClientError,
    SessionSetupError,
    decode_version_str,
)
from acconeer.exptool.a111._clients.reg import protocol, regmap
from acconeer.exptool.a111._modes import Mode


log = logging.getLogger(__name__)

ModeInfo = namedtuple("ModeInfo", ["fixed_buffer_size", "byte_per_element"])

MODE_INFOS = {
    Mode.POWER_BINS: ModeInfo(True, 2),
    Mode.ENVELOPE: ModeInfo(True, 2),
    Mode.IQ: ModeInfo(True, 4),
    Mode.SPARSE: ModeInfo(True, 2),
}


class RegBaseClient(BaseClient):
    _STATUS_TIMEOUT = 3.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._streaming_control_val = "no_streaming"  # Override in subclass (UART)

        self._mode = None
        self._config = None
        self._data_length = None

    def _setup_session(self, config):
        if len(config.sensor) > 1:
            raise ValueError("the register protocol does not support multiple sensors")
        if config.sensor[0] != 1:
            raise ValueError("the register protocol currently only supports using sensor 1")

        mode = config.mode
        self._mode = mode
        self._config = config

        self._write_reg("main_control", "stop")
        self._write_reg("mode_selection", mode)
        self._write_reg("update_rate", 0)
        self._write_reg("sensor_power_mode", "active")

        for key, reg in regmap.get_config_key_to_reg_map(mode).items():
            val = getattr(config, key)

            if val is None:
                continue

            self._write_reg(reg, val)

        self._write_reg("streaming_control", self._streaming_control_val)

        self._write_reg("main_control", "create")
        self._wait_status(regmap.STATUS_FLAGS.CREATED)

        info = {}
        info_regs = regmap.get_session_info_regs(mode)
        for reg in info_regs:
            k = reg.stripped_name
            k = regmap.STRIPPED_NAME_TO_INFO_REMAP.get(k, k)

            if k is None:
                continue

            info[k] = self._read_reg(reg)

        if MODE_INFOS[mode].fixed_buffer_size:
            self._data_length = info.get("data_length")

            log.info("data length: {}".format(self._data_length))
            log.info("buffer size: {} B".format(self._buffer_size))
        else:
            self._data_length = None

        if self._data_rate is not None:
            log.info("requested data rate: {:.2f} Mbit/s".format(self._data_rate * 1e-6))

        return info

    def _wait_status(self, val, mask=None):
        val = regmap.STATUS_FLAGS(val)

        if mask is None:
            mask = val
        else:
            mask = regmap.STATUS_FLAGS(mask)

        start_time = time()

        while time() - start_time < self._STATUS_TIMEOUT:
            status = self._read_reg(regmap.STATUS_REG)

            status_error = status & regmap.STATUS_MASKS.ERROR_MASK

            if status_error:
                if status_error & regmap.STATUS_FLAGS.ERROR_CREATION:
                    raise SessionSetupError
                else:
                    raise ClientError("server error: " + str(status_error).split(".")[1])

            if (status & mask) == val:
                return

        raise ClientError("timeout while waiting for status")

    def _get_supported_modes(self):
        supported_modes = set()
        self._write_reg("main_control", "clear_status")

        for mode in Mode:
            self._write_reg("mode_selection", mode)
            status = self._read_reg("status")

            if status & regmap.STATUS_FLAGS.ERROR_SET_MODE:
                self._write_reg("main_control", "clear_status")
            else:
                supported_modes.add(mode)

        return supported_modes

    @property
    def _buffer_size(self):  # B
        if self._data_length is None or self._mode is None:
            return None

        return self._data_length * MODE_INFOS[self._mode].byte_per_element

    @property
    def _data_rate(self):  # Mbit/s
        if self._buffer_size is None or self._config.update_rate is None:
            return None

        return self._buffer_size * 8 * self._config.update_rate

    @abc.abstractmethod
    def _read_reg(self, reg):
        pass

    @abc.abstractmethod
    def _write_reg(self, reg, val):
        pass


class UARTClient(RegBaseClient):
    DEFAULT_BASE_BAUDRATE = 115200
    CONNECT_ROUTINE_TIMEOUT = 0.6

    def __init__(self, port, **kwargs):
        self.override_baudrate = kwargs.pop("override_baudrate", None)

        super().__init__(**kwargs)

        self._streaming_control_val = "uart_streaming"

        if platform.system().lower() in ["windows", "darwin"]:
            self._link = links.SerialLink(port)
        else:
            self._link = links.SerialProcessLink(port)

    def _connect(self):
        self._link.timeout = self.CONNECT_ROUTINE_TIMEOUT

        if self.override_baudrate:
            self._link.baudrate = self.override_baudrate
            self._link.connect()

            try:
                self._handshake()
            except links.LinkError as e:
                raise ClientError("could not connect, no response") from e
        else:
            baudrates = [int(3e6), int(1e6)]
            baudrates.append(self.DEFAULT_BASE_BAUDRATE)
            baudrates = sorted(list(set(baudrates)))

            self._link.baudrate = baudrates[0]
            self._link.connect()

            for i, baudrate in enumerate(baudrates):
                if i != 0:
                    self._link.baudrate = baudrate
                    sleep(0.2)

                try:
                    self._handshake()
                except links.LinkError:
                    log.debug("handshake failed at {} baud".format(baudrate))
                else:
                    log.debug("handshake succeeded at {} baud".format(baudrate))
                    break
            else:
                raise ClientError("could not connect, no response")

            product_max_baudrate = self._read_reg("product_max_uart_baudrate")

            if baudrate != product_max_baudrate:
                log.debug("switching to {} baud...".format(product_max_baudrate))
                self._write_reg("uart_baudrate", product_max_baudrate)
                self._link.baudrate = product_max_baudrate
                sleep(0.2)
                self._handshake()
                log.debug("handshake succeeded at {} baud".format(product_max_baudrate))

        self._link.timeout = self._link.DEFAULT_TIMEOUT

        version_buffer = self._read_buf_raw()
        version_info = decode_version_buffer(version_buffer)

        info = {}
        info.update(version_info)

        return info

    def _setup_session(self, config):
        ret = super()._setup_session(config)

        if self._config.update_rate:
            self._link.timeout = 1 / self._config.update_rate + self._link.DEFAULT_TIMEOUT
        else:
            self._link.timeout = self._link.DEFAULT_TIMEOUT

        if self._data_rate is not None:
            if self._data_rate > 2 / 3 * self._link.baudrate:
                log.warning("data rate might be too high")

        return ret

    def _start_session(self):
        self._write_reg("main_control", "activate")
        # self._wait_status(regmap.STATUS_FLAGS.ACTIVATED)
        # TODO: how can we handle streaming and reading/writing registers at the same time?

    def _get_next(self):
        packet = self._recv_packet(allow_recovery_skip=True)

        if not isinstance(packet, protocol.StreamData):
            raise ClientError("got unexpected type of frame")

        info = {}
        for addr, enc_val in packet.result_info:
            try:
                reg = regmap.get_reg(addr, self._mode)
                val = reg.decode(enc_val)
            except (protocol.ProtocolError, ValueError):
                log.info("got unknown reg val in result info")
                log.info("addr: {}, value: {}".format(addr, fmt_enc_val(enc_val)))
            else:
                k = reg.stripped_name
                k = regmap.STRIPPED_NAME_TO_INFO_REMAP.get(k, k)

                if k is None:
                    continue

                info[k] = val

        sweeps_per_frame = getattr(self._config, "sweeps_per_frame", None)
        data = protocol.decode_output_buffer(packet.buffer, self._mode, sweeps_per_frame)

        if self.squeeze:
            return info, data
        else:
            return [info], np.expand_dims(data, 0)

    def _stop_session(self):
        self._write_reg("main_control", "stop", expect_response=False)

        t0 = time()
        while time() - t0 < self._link.timeout:
            res = self._recv_packet()

            if isinstance(res, protocol.RegWriteResponse):
                break
            if not isinstance(res, protocol.StreamData):
                raise ClientError("got unexpected packet while stopping session")
        else:
            raise ClientError("timeout while stopping session")

        self._link.timeout = self._link.DEFAULT_TIMEOUT

        mask = regmap.STATUS_FLAGS.CREATED | regmap.STATUS_FLAGS.ACTIVATED
        self._wait_status(0, mask=mask)

    def _disconnect(self):
        self._write_reg("uart_baudrate", self.DEFAULT_BASE_BAUDRATE)
        self._link.disconnect()

    def _read_buf_raw(self, addr=protocol.MAIN_BUFFER_ADDR):
        req = protocol.BufferReadRequest(addr)
        self._send_packet(req)

        log.debug("sent buf r req: addr: 0x{:02x}".format(addr))

        res = self._recv_packet()
        if not isinstance(res, protocol.BufferReadResponse):
            raise ClientError("got unexpected type of frame")

        log.debug("recv buf r res: addr: 0x{:02x} len: {}".format(addr, len(res.buffer)))

        return res.buffer

    def _read_reg(self, reg, mode=None):
        mode = self._mode if mode is None else mode
        reg = regmap.get_reg(reg, mode)
        enc_val = self._read_reg_raw(reg.addr)
        return reg.decode(enc_val)

    def _read_reg_raw(self, addr):
        addr = regmap.get_reg_addr(addr)
        req = protocol.RegReadRequest(addr)
        self._send_packet(req)

        log.debug("sent reg r req: addr: 0x{:02x}".format(addr))

        res = self._recv_packet()
        if not isinstance(res, protocol.RegReadResponse):
            raise ClientError("got unexpected type of frame")

        enc_val = res.reg_val.val

        log.debug("recv reg r res: addr: 0x{:02x} val: {}".format(addr, fmt_enc_val(enc_val)))

        return enc_val

    def _write_reg(self, reg, val, expect_response=True):
        reg = regmap.get_reg(reg, self._mode)
        enc_val = reg.encode(val)
        self._write_reg_raw(reg.addr, enc_val, expect_response)

    def _write_reg_raw(self, addr, enc_val, expect_response=True):
        addr = regmap.get_reg_addr(addr)
        rrv = protocol.RegVal(addr, enc_val)
        req = protocol.RegWriteRequest(rrv)
        self._send_packet(req)

        log.debug("sent reg w req: addr: 0x{:02x} val: {}".format(addr, fmt_enc_val(enc_val)))

        if expect_response:
            res = self._recv_packet()
            if not isinstance(res, protocol.RegWriteResponse):
                raise ClientError("got unexpected packet (expected reg write response)")
            if res.reg_val != rrv:
                raise ClientError("reg write failed")

            log.debug("recv reg w res: ok")

    def _send_packet(self, packet):
        frame = protocol.insert_packet_into_frame(packet)
        self._link.send(frame)

    def _recv_packet(self, allow_recovery_skip=False):
        buf_1 = self._link.recv(1 + protocol.LEN_FIELD_SIZE)

        start_marker = buf_1[0]
        packet_len = int.from_bytes(buf_1[1:], protocol.BO)

        if start_marker != protocol.START_MARKER:
            raise ClientError("got invalid frame (incorrect start marker)")

        buf_2 = self._link.recv(packet_len + 2)
        packet = buf_2[:-1]
        end_marker = buf_2[-1]

        if end_marker != protocol.END_MARKER:
            if not allow_recovery_skip:
                raise ClientError("got invalid frame (incorrect end marker)")

            log.debug("got invalid frame (incorrect end marker), attempting recovery")

            buf_2.extend(self._link.recv(1 + protocol.LEN_FIELD_SIZE))

            si = 0
            ei = len(buf_2)
            expected_sub_len = protocol.LEN_FIELD_SIZE + packet_len + 3
            while True:
                si = buf_2.find(buf_1, si, ei)
                if si < 0:
                    raise ClientError("got invalid frame and could not recover")

                sub_len_diff = expected_sub_len - (len(buf_2) - si)

                if sub_len_diff > 0:
                    buf_2.extend(self._link.recv(sub_len_diff))

                if buf_2[-1] != protocol.END_MARKER:
                    log.debug("recovery attempt failed")
                    continue

                packet = buf_2[si + 1 + protocol.LEN_FIELD_SIZE : -1]
                break

            log.warning("successfully recovered from corrupt frame")

        return protocol.unpack_packet(packet)

    def _handshake(self):
        self._write_reg("main_control", "stop", expect_response=False)

        exp_addr = regmap.get_reg_addr("main_control")
        exp_enc_val = regmap.get_reg("main_control").encode("stop")
        exp_reg_val = protocol.RegVal(exp_addr, exp_enc_val)
        exp_packet = protocol.RegWriteResponse(exp_reg_val)
        exp_frame = protocol.insert_packet_into_frame(exp_packet)
        self._link.recv_until(exp_frame)

    @property
    def description(self):
        return f"UART ({self._link._port})"


class PollingUARTClient(UARTClient):
    def __init__(self, port, **kwargs):
        self._measure_on_call = kwargs.pop("measure_on_call", True)

        super().__init__(port, **kwargs)
        self._streaming_control_val = "no_streaming"
        self._link = links.SerialLink(port)  # don't use link in separate process

    def _start_session(self):
        self._write_reg("main_control", "activate")
        self._wait_status(regmap.STATUS_FLAGS.ACTIVATED)

    def _get_next(self):
        if self._measure_on_call:
            self._write_reg("main_control", "clear_status")

        poll_t = time()

        while True:
            status = self._read_reg("status")

            if status & regmap.STATUS_MASKS.ERROR_MASK:
                raise ClientError("server error: " + str(status).split(".")[1])
            elif status & regmap.STATUS_FLAGS.DATA_READY:
                break
            else:
                if (time() - poll_t) > self._link.timeout:
                    raise ClientError("gave up polling")

                continue

        buffer = self._read_buf_raw()

        info = {}
        info_regs = regmap.get_data_info_regs(self._config.mode)
        for reg in info_regs:
            k = reg.stripped_name
            k = regmap.STRIPPED_NAME_TO_INFO_REMAP.get(k, k)

            if k is None:
                continue

            info[k] = self._read_reg(reg)

        if not self._measure_on_call:
            self._write_reg("main_control", "clear_status")

        sweeps_per_frame = getattr(self._config, "sweeps_per_frame", None)
        data = protocol.decode_output_buffer(buffer, self._mode, sweeps_per_frame)

        if self.squeeze:
            return info, data
        else:
            return [info], np.expand_dims(data, 0)

    def _stop_session(self):
        self._write_reg("main_control", "stop")

        mask = regmap.STATUS_FLAGS.CREATED | regmap.STATUS_FLAGS.ACTIVATED
        self._wait_status(0, mask=mask)


class SPIClient(RegBaseClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._proc = None

    def _connect(self):
        self._cmd_queue = mp.Queue()
        self._data_queue = mp.Queue()
        args = (
            self._cmd_queue,
            self._data_queue,
        )
        self._proc = SPICommProcess(*args)
        self._proc.start()

        self.__cmd_proc("connect")

        log.debug("connected")

        version_buffer = self._read_main_buffer()
        version_info = decode_version_buffer(version_buffer)

        info = {}
        info.update(version_info)

        return info

    def _setup_session(self, config):
        ret = super()._setup_session(config)
        update_rate = self._config.update_rate
        self.__cmd_proc("update_state", self._mode, update_rate, self._buffer_size)
        return ret

    def _start_session(self):
        self._write_reg("main_control", "activate")
        self._wait_status(regmap.STATUS_FLAGS.ACTIVATED)

        if self._buffer_size is not None:
            self._wait_status(regmap.STATUS_FLAGS.DATA_READY)
            reported_buffer_size = self._read_reg("output_buffer_length")
            assert self._buffer_size == reported_buffer_size

        self.__cmd_proc("start_session")

    def _get_next(self):
        ret_cmd, ret_args = self._data_queue.get()
        if ret_cmd == "error":
            raise ClientError("exception raised in SPI communcation process")
        elif ret_cmd != "get_next":
            raise ClientError
        info, buffer = ret_args

        sweeps_per_frame = getattr(self._config, "sweeps_per_frame", None)
        data = protocol.decode_output_buffer(buffer, self._mode, sweeps_per_frame)

        if self.squeeze:
            return info, data
        else:
            return [info], np.expand_dims(data, 0)

    def _stop_session(self):
        self.__cmd_proc("stop_session")

        mask = regmap.STATUS_FLAGS.CREATED | regmap.STATUS_FLAGS.ACTIVATED
        self._wait_status(0, mask=mask)

    def _disconnect(self):
        self.__cmd_proc("disconnect")
        self._proc.join(1)

    def _read_reg(self, reg):
        reg = regmap.get_reg(reg, self._mode)
        enc_val = self._read_reg_raw(reg.addr)
        return reg.decode(enc_val)

    def _read_reg_raw(self, addr):
        addr = regmap.get_reg_addr(addr)
        enc_val = self.__cmd_proc("read_reg_raw", addr)
        return enc_val

    def _write_reg(self, reg, val):
        reg = regmap.get_reg(reg, self._mode)
        enc_val = reg.encode(val)
        self._write_reg_raw(reg.addr, enc_val)

    def _write_reg_raw(self, addr, enc_val):
        addr = regmap.get_reg_addr(addr)
        self.__cmd_proc("write_reg_raw", addr, enc_val)

    def read_buf_raw(self, addr, size):
        addr = regmap.get_reg_addr(addr)
        buffer = self.__cmd_proc("read_buf_raw", addr, size)
        return buffer

    def _read_main_buffer(self):
        buffer_size = self._read_reg("output_buffer_length")
        if buffer_size > 0:
            buffer = self.read_buf_raw(protocol.MAIN_BUFFER_ADDR, buffer_size)
        else:
            buffer = bytearray()
        return buffer

    def __cmd_proc(self, cmd, *args):
        log.debug("sending cmd to proc: {}".format(cmd))
        self._cmd_queue.put((cmd, args))
        if cmd == "stop_session":
            while True:
                ret_cmd, _ = self._data_queue.get()
                if ret_cmd == cmd:
                    break
                elif ret_cmd == "error":
                    raise ClientError("exception raised in SPI communcation process")
                elif ret_cmd != "get_next":
                    raise ClientError
            ret_args = None
        else:
            ret_cmd, ret_args = self._data_queue.get()
            if ret_cmd == "error":
                raise ClientError("exception raised in SPI communcation process")
            elif ret_cmd != cmd:
                raise ClientError
        return ret_args

    @property
    def description(self):
        return "SPI"


class SPICommProcess(mp.Process):
    def __init__(self, cmd_q, data_q):
        super().__init__(daemon=True)
        self.cmd_q = cmd_q
        self.data_q = data_q
        self.mode = None

    def run(self):
        self.log = logging.getLogger(__name__)
        self.log.debug("SPI communication process started")
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        try:
            self._run()
        except Exception:
            print("Exception raised in SPI communication process:\n", file=sys.stderr)
            traceback.print_exc()
            print("\n\n", file=sys.stderr)
            self.data_q.put(("error", ()))

        while True:
            try:
                self.cmd_q.get(timeout=0.01)
            except queue.Empty:
                break

    def _run(self):
        while True:
            (cmd, cmd_args) = self.cmd_q.get()

            if hasattr(self, cmd):
                ret = getattr(self, cmd)(*cmd_args)
                self.data_q.put((cmd, ret))

                if cmd == "start_session":
                    self.poll()
                elif cmd == "disconnect":
                    break
            else:
                raise ClientError("unknown cmd {}".format(cmd))

    def poll(self):
        while self.cmd_q.empty():
            ret = self.get_next()
            self.data_q.put(("get_next", ret))

    def get_next(self):
        poll_t = time()

        while True:
            status = self.read_reg("status", do_log=False)

            if status & regmap.STATUS_MASKS.ERROR_MASK:
                raise ClientError("server error: " + str(status).split(".")[1])
            elif status & regmap.STATUS_FLAGS.DATA_READY:
                break
            else:
                if (time() - poll_t) > self.poll_timeout:
                    raise ClientError("gave up polling")

                continue

        buffer_size = self.fixed_buf_size or self.read_reg("output_buffer_length")
        if buffer_size > 0:
            buffer = self.read_buf_raw(protocol.MAIN_BUFFER_ADDR, buffer_size)
        else:
            buffer = bytearray()

        info = {}
        info_regs = regmap.get_data_info_regs(self.mode)
        for reg in info_regs:
            k = reg.stripped_name
            k = regmap.STRIPPED_NAME_TO_INFO_REMAP.get(k, k)

            if k is None:
                continue

            info[k] = self.read_reg(reg, do_log=False)

        self.write_reg("main_control", "clear_status", do_log=False)

        return info, buffer

    def connect(self):
        self.dev = libft4222.Device()
        self.dev.open_ex()
        self.dev.set_clock(libft4222.ClockRate.SYS_CLK_48)
        self.dev.spi_master_init(clock=libft4222.SPIClock.CLK_DIV_2)
        self.dev.spi_set_driving_strength()
        self.dev.set_timeouts(1000, 1000)
        self.dev.set_suspend_out(False)
        self.dev.set_wake_up_interrupt(False)

    def update_state(self, mode, update_rate, buffer_size):
        self.mode = mode

        if update_rate is None:
            self.poll_timeout = 1.0
        else:
            self.poll_timeout = 2 / update_rate + 0.5

        self.fixed_buf_size = buffer_size

    def start_session(self):
        pass

    def stop_session(self):
        self.write_reg("main_control", "stop")

    def disconnect(self):
        self.dev.close()

    def read_reg(self, reg, do_log=True):
        reg = regmap.get_reg(reg, self.mode)
        enc_val = self.read_reg_raw(reg.addr, do_log=do_log)
        return reg.decode(enc_val)

    def read_reg_raw(self, addr, do_log=True):
        addr = regmap.get_reg_addr(addr)
        b = bytearray([protocol.REG_READ_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        enc_val = self.dev.spi_master_single_read(4)
        if do_log:
            log.debug("reg r res: addr: 0x{:02x} val: {}".format(addr, fmt_enc_val(enc_val)))
        return enc_val

    def write_reg(self, reg, val, do_log=True):
        reg = regmap.get_reg(reg, self.mode)
        enc_val = reg.encode(val)
        self.write_reg_raw(reg.addr, enc_val, do_log=do_log)

    def write_reg_raw(self, addr, enc_val, do_log=True):
        addr = regmap.get_reg_addr(addr)
        b = bytearray([protocol.REG_WRITE_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        if do_log:
            log.debug("reg w req: addr: 0x{:02x} val: {}".format(addr, fmt_enc_val(enc_val)))
        self.dev.spi_master_single_write(enc_val)

    def read_buf_raw(self, addr, size):
        b = bytearray([protocol.BUF_READ_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        return self.dev.spi_master_single_read(size)


def fmt_enc_val(enc_val):
    return " ".join(["{:02x}".format(x) for x in enc_val])


def decode_version_buffer(version: bytearray) -> dict:
    try:
        version_str = version.decode("ascii").strip()
        assert len(version_str) > 1
    except (UnicodeDecodeError, AssertionError):
        return {}

    return decode_version_str(version_str)
