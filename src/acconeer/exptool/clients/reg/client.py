import numpy as np
import logging
from time import time, sleep
import multiprocessing as mp
import queue
import signal
import traceback
import platform

from acconeer.exptool.clients.base import BaseClient, ClientError, decode_version_str
from acconeer.exptool.clients.reg import protocol, utils
from acconeer.exptool.clients import links
from acconeer.exptool import libft4222


log = logging.getLogger(__name__)

SPI_MAIN_CTRL_SLEEP = 0.3


class UARTClient(BaseClient):
    _XM112_LED_PIN = 67

    DEFAULT_BASE_BAUDRATE = 115200
    CONNECT_ROUTINE_TIMEOUT = 0.6

    def __init__(self, port, **kwargs):
        super().__init__(**kwargs)

        if platform.system().lower() == "windows":
            self._link = links.SerialLink(port)
        else:
            self._link = links.SerialProcessLink(port)

        self.override_baudrate = kwargs.get("override_baudrate")

        self._mode = protocol.NO_MODE
        self._num_subsweeps = None

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
            baudrates = [product.baudrate for product in protocol.PRODUCTS]
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

            product_id = self._read_reg("product_id")
            product = {product.id: product for product in protocol.PRODUCTS}[product_id]

            if baudrate != product.baudrate:
                log.debug("switching to {} baud...".format(product.baudrate))
                self._write_reg("uart_baudrate", product.baudrate)
                self._link.baudrate = product.baudrate
                sleep(0.2)
                self._handshake()
                log.debug("handshake succeeded at {} baud".format(product.baudrate))

        self._link.timeout = self._link.DEFAULT_TIMEOUT

        ver = self._read_reg("product_version")
        if ver < protocol.MIN_VERSION:
            log.warning("server version is not supported (too old)")
        elif ver != protocol.DEV_VERSION:
            log.warning("server version might not be fully supported")

        version_buffer = self._read_buf_raw()
        version_info = decode_version_buffer(version_buffer)

        info = {}
        info.update(version_info)

        return info

    def _setup_session(self, config):
        if len(config.sensor) > 1:
            raise ValueError("the register protocol does not support multiple sensors")
        if config.sensor[0] != 1:
            raise ValueError("the register protocol currently only supports using sensor 1")

        mode = protocol.get_mode(config.mode)
        self._mode = mode

        self._write_reg("main_control", "stop")

        self._write_reg("mode_selection", mode)

        if config.experimental_stitching:
            self._write_reg("repetition_mode", "max")
            log.warning("experimental stitching on - switching to max freq. mode")
        else:
            self._write_reg("repetition_mode", "fixed")

        self._write_reg("streaming_control", "uart")
        self._write_reg("sensor_power_mode", "d")

        if mode == "iq":
            self._write_reg("output_data_compression", 1)

        rvs = utils.get_reg_vals_for_config(config)
        for rv in rvs:
            self._write_reg_raw(rv.addr, rv.val)

        self._write_reg("main_control", "create")
        status = self._read_reg("status")

        if status & protocol.STATUS_ERROR_ON_SERVICE_CREATION_MASK:
            raise ClientError("session setup failed")

        info = {}
        info_regs = utils.get_session_info_regs(mode)
        for reg in info_regs:
            info[reg.name] = self._read_reg(reg, mode)

        self._num_subsweeps = info.get("number_of_subsweeps")

        # data rate check
        data_length = info.get("data_length")
        freq = info.get("frequency")
        bpp = protocol.BYTE_PER_POINT.get(mode)
        if data_length:
            log.debug("data length: {}".format(data_length))

            if bpp and freq and not config.experimental_stitching:
                data_rate = 8 * bpp * data_length * freq
                log_text = "data rate: {:.2f} Mbit/s".format(data_rate*1e-6)
                if data_rate > 2/3 * self._link.baudrate:
                    log.warning(log_text)
                    log.warning("data rate might be too high")
                else:
                    log.info(log_text)

        return info

    def _start_session(self):
        self._write_reg("main_control", "activate")

    def _get_next(self):
        packet = self._recv_packet(allow_recovery_skip=True)

        if not isinstance(packet, protocol.StreamData):
            raise ClientError("got unexpected type of frame")

        info = {}
        for addr, enc_val in packet.result_info:
            try:
                reg = protocol.get_reg(addr, self._mode)
                val = protocol.decode_reg_val(reg, enc_val)
            except protocol.ProtocolError:
                log.info("got unknown reg val in result info")
                log.info("addr: {}, value: {}".format(addr, fmt_enc_val(enc_val)))
            else:
                info[reg.name] = val

        data = protocol.decode_output_buffer(packet.buffer, self._mode, self._num_subsweeps)

        if self.squeeze:
            return info, data
        else:
            return [info], np.expand_dims(data, 0)

    def _stop_session(self):
        self._write_reg("main_control", "stop", expect_response=False)

        t0 = time()
        while time() - t0 < self._link._timeout:
            res = self._recv_packet()

            if isinstance(res, protocol.RegWriteResponse):
                break
            if not isinstance(res, protocol.StreamData):
                raise ClientError("got unexpected packet while stopping session")
        else:
            raise ClientError("timeout while stopping session")

    def _disconnect(self):
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
        mode = mode or self._mode
        reg = protocol.get_reg(reg, mode)
        enc_val = self._read_reg_raw(reg.addr)
        return protocol.decode_reg_val(reg, enc_val)

    def _read_reg_raw(self, addr):
        addr = protocol.get_addr_for_reg(addr)
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
        reg = protocol.get_reg(reg, self._mode)
        enc_val = protocol.encode_reg_val(reg, val)
        self._write_reg_raw(reg.addr, enc_val, expect_response)

    def _write_reg_raw(self, addr, enc_val, expect_response=True):
        addr = protocol.get_addr_for_reg(addr)
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

    def _read_gpio(self, pin):
        req = protocol.GPIOPin(pin)
        self._send_packet(req)

        res = self._recv_packet()

        if not isinstance(res, protocol.GPIOPinAndVal):
            raise ClientError("got unexpected packet (expected gpio pin and value)")

        return res.val

    def _write_gpio(self, pin, val):
        req = protocol.GPIOPinAndVal(pin, val)
        self._send_packet(req)

        res = self._recv_packet()
        if not isinstance(res, protocol.GPIOPinAndVal):
            raise ClientError("got unexpected packet (expected gpio pin and value)")
        if res.val != val:
            raise ClientError("gpio write failed")

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

                packet = buf_2[si+1+protocol.LEN_FIELD_SIZE:-1]
                break

            log.warning("successfully recovered from corrupt frame")

        return protocol.unpack_packet(packet)

    def _handshake(self):
        self._write_reg("main_control", "stop", expect_response=False)

        exp_addr = protocol.get_addr_for_reg("main_control")
        exp_enc_val = protocol.encode_reg_val("main_control", "stop")
        exp_reg_val = protocol.RegVal(exp_addr, exp_enc_val)
        exp_packet = protocol.RegWriteResponse(exp_reg_val)
        exp_frame = protocol.insert_packet_into_frame(exp_packet)
        self._link.recv_until(exp_frame)

        idn_reg = self._read_reg("product_id")
        possible_ids = [product.id for product in protocol.PRODUCTS]
        if idn_reg not in possible_ids:
            raise ClientError("unexpected product id")


class SPIClient(BaseClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._mode = protocol.NO_MODE
        self._proc = None
        self._num_subsweeps = None
        self._experimental_stitching = None

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

        idn_reg = self._read_reg("product_id")
        possible_ids = [product.id for product in protocol.PRODUCTS]
        if idn_reg not in possible_ids:
            raise ClientError("unexpected product id")

        ver = self._read_reg("product_version")
        if ver < protocol.MIN_VERSION:
            log.warning("server version is not supported (too old)")
        elif ver != protocol.DEV_VERSION:
            log.warning("server version might not be fully supported")

        version_buffer = self._read_main_buffer()
        version_info = decode_version_buffer(version_buffer)

        info = {}
        info.update(version_info)

        return info

    def _setup_session(self, config):
        if len(config.sensor) > 1:
            raise ValueError("the register protocol does not support multiple sensors")
        if config.sensor[0] != 1:
            raise ValueError("the register protocol currently only supports using sensor 1")

        mode = protocol.get_mode(config.mode)
        self._mode = mode

        self._experimental_stitching = bool(config.experimental_stitching)
        sweep_rate = None if config.experimental_stitching else config.sweep_rate
        self.__cmd_proc("set_mode_and_rate", mode, sweep_rate)

        self._write_reg("main_control", "stop")

        self._write_reg("mode_selection", mode)

        if config.experimental_stitching:
            self._write_reg("repetition_mode", "max")
            log.warning("experimental stitching on - switching to max freq. mode")
        else:
            self._write_reg("repetition_mode", "fixed")

        self._write_reg("streaming_control", "disable")
        self._write_reg("sensor_power_mode", "d")

        if mode == "iq":
            self._write_reg("output_data_compression", 1)

        rvs = utils.get_reg_vals_for_config(config)
        for rv in rvs:
            self._write_reg_raw(rv.addr, rv.val)

        self._write_reg("main_control", "create")
        sleep(SPI_MAIN_CTRL_SLEEP)
        status = self._read_reg("status")

        if status & protocol.STATUS_ERROR_ON_SERVICE_CREATION_MASK:
            raise ClientError("session setup failed")

        info = {}
        info_regs = utils.get_session_info_regs(mode)
        for reg in info_regs:
            info[reg.name] = self._read_reg(reg)

        self._num_subsweeps = info.get("number_of_subsweeps")

        # data rate check
        data_length = info.get("data_length")
        freq = info.get("frequency")
        bpp = protocol.BYTE_PER_POINT.get(mode)
        if data_length:
            log.debug("assumed data length: {}".format(data_length))

            if bpp and freq and not config.experimental_stitching:
                data_rate = 8 * bpp * data_length * freq
                log_text = "data rate: {:.2f} Mbit/s".format(data_rate*1e-6)
                log.info(log_text)

        return info

    def _start_session(self):
        self.__cmd_proc("start_session")
        self._seq_num = None

    def _get_next(self):
        ret_cmd, ret_args = self._data_queue.get()
        if ret_cmd == "error":
            raise ClientError("exception raised in SPI communcation process")
        elif ret_cmd != "get_next":
            raise ClientError
        info, buffer = ret_args

        data = protocol.decode_output_buffer(buffer, self._mode, self._num_subsweeps)

        if not self._experimental_stitching:
            cur_seq_num = info.get("sequence_number")
            if cur_seq_num:
                if self._seq_num:
                    if cur_seq_num > self._seq_num + 1:
                        log.info("missed sweep")
                    if cur_seq_num <= self._seq_num:
                        log.info("got same sweep twice")
                self._seq_num = cur_seq_num

        if self.squeeze:
            return info, data
        else:
            return [info], np.expand_dims(data, 0)

    def _stop_session(self):
        self.__cmd_proc("stop_session")

    def _disconnect(self):
        self.__cmd_proc("disconnect")
        self._proc.join(1)

    def _read_reg(self, reg):
        reg = protocol.get_reg(reg, self._mode)
        enc_val = self._read_reg_raw(reg.addr)
        return protocol.decode_reg_val(reg, enc_val)

    def _read_reg_raw(self, addr):
        addr = protocol.get_addr_for_reg(addr)
        enc_val = self.__cmd_proc("read_reg_raw", addr)
        return enc_val

    def _write_reg(self, reg, val):
        reg = protocol.get_reg(reg, self._mode)
        enc_val = protocol.encode_reg_val(reg, val)
        self._write_reg_raw(reg.addr, enc_val)

    def _write_reg_raw(self, addr, enc_val):
        addr = protocol.get_addr_for_reg(addr)
        self.__cmd_proc("write_reg_raw", addr, enc_val)

    def read_buf_raw(self, addr, size):
        addr = protocol.get_addr_for_reg(addr)
        buffer = self.__cmd_proc("read_buf_raw", addr, size)
        return buffer

    def _read_main_buffer(self):
        buffer_size = self._read_reg("output_data_buffer_length")
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


class SPICommProcess(mp.Process):
    def __init__(self, cmd_q, data_q):
        super().__init__(daemon=True)
        self.cmd_q = cmd_q
        self.data_q = data_q
        self.mode = None
        self.consecutive_error_count = 0

    def run(self):
        self.log = logging.getLogger(__name__)
        self.log.debug("SPI communication process started")
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        try:
            self._run()
        except Exception:
            print("Exception raised in SPI communication process:\n")
            traceback.print_exc()
            print("\n\n")
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
        self.consecutive_error_count = 0

        while self.cmd_q.empty():
            ret = self.get_next()
            self.data_q.put(("get_next", ret))

    def get_next(self):
        poll_t = time()
        while True:
            status = self.read_reg("status", do_log=False)
            if not status:
                if (time() - poll_t) > self.poll_timeout:
                    raise ClientError("gave up polling")
                continue
            elif status & protocol.STATUS_DATA_READY_MASK:
                self.consecutive_error_count = 0
                break
            elif status & protocol.STATUS_ERROR_MASK:
                self.write_reg("main_control", "clear_status")
                log.info("lost sweep due to server error")

                self.consecutive_error_count += 1
                if self.consecutive_error_count >= 3:
                    raise ClientError("too many server errors")
            else:
                raise ClientError("got unexpected status ({})".format(status))

        buffer_size = self.fixed_buf_size or self.read_reg("output_data_buffer_length")
        if buffer_size > 0:
            buffer = self.read_buf_raw(protocol.MAIN_BUFFER_ADDR, buffer_size)
        else:
            buffer = bytearray()

        info = {}
        info_regs = utils.get_sweep_info_regs(self.mode)
        for reg in info_regs:
            info[reg.name] = self.read_reg(reg, do_log=False)

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

    def set_mode_and_rate(self, mode, sweep_rate):
        self.mode = mode
        if sweep_rate:
            self.poll_timeout = (2/sweep_rate + 0.5)
        else:
            self.poll_timeout = 1.0

    def start_session(self):
        self.write_reg("main_control", "activate")
        sleep(SPI_MAIN_CTRL_SLEEP)
        self.write_reg("main_control", "clear_status")

        if protocol.FIXED_BUF_SIZE.get(self.mode):
            self.fixed_buf_size = self.read_reg("output_data_buffer_length")
            log.info("using fixed buffer size of {}".format(self.fixed_buf_size))
            if self.fixed_buf_size == 0:
                raise ClientError("got unexpected buffer length of 0")
        else:
            self.fixed_buf_size = None

    def stop_session(self):
        self.write_reg("main_control", "stop")

    def disconnect(self):
        self.dev.close()

    def read_reg(self, reg, do_log=True):
        reg = protocol.get_reg(reg, self.mode)
        enc_val = self.read_reg_raw(reg.addr, do_log=do_log)
        return protocol.decode_reg_val(reg, enc_val)

    def read_reg_raw(self, addr, do_log=True):
        addr = protocol.get_addr_for_reg(addr)
        b = bytearray([protocol.REG_READ_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        enc_val = self.dev.spi_master_single_read(4)
        if do_log:
            log.debug("reg r res: addr: 0x{:02x} val: {}".format(addr, fmt_enc_val(enc_val)))
        return enc_val

    def write_reg(self, reg, val, do_log=True):
        reg = protocol.get_reg(reg, self.mode)
        enc_val = protocol.encode_reg_val(reg, val)
        self.write_reg_raw(reg.addr, enc_val, do_log=do_log)

    def write_reg_raw(self, addr, enc_val, do_log=True):
        addr = protocol.get_addr_for_reg(addr)
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


def decode_version_buffer(version: bytearray):
    try:
        version_str = version.decode("ascii").strip()
        assert len(version_str) > 1
        assert version_str.startswith("v")
        version_str = version_str[1:]
    except (UnicodeDecodeError, AssertionError):
        return {}

    return decode_version_str(version_str)
