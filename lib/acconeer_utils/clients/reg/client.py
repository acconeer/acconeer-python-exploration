import numpy as np
import logging
from time import time, sleep
import multiprocessing as mp
import queue
import signal
import traceback
import platform

from acconeer_utils.clients.base import BaseClient, ClientError
from acconeer_utils.clients.reg import protocol, utils
from acconeer_utils.clients import links
from acconeer_utils import libft4222


log = logging.getLogger(__name__)

SPI_MAIN_CTRL_SLEEP = 0.3


class RegClient(BaseClient):
    def __init__(self, port, **kwargs):
        super().__init__(**kwargs)

        if platform.system().lower() == "windows":
            self._link = links.SerialLink(port)
        else:
            self._link = links.SerialProcessLink(port)

        self._mode = protocol.NO_MODE
        self._num_subsweeps = None

    def _connect(self):
        max_baud = links.BaseSerialLink.MAX_BAUDRATE
        default_baud = links.BaseSerialLink.DEFAULT_BAUDRATE

        self._link.baudrate = max_baud
        self._link.connect()

        log.debug("connected at {} baud".format(max_baud))

        success = False
        try:
            self._handshake()
        except ClientError:
            log.info("handshake failed at {} baud, trying {} baud..."
                     .format(max_baud, default_baud))
        else:
            success = True

        if not success:
            self._link.disconnect()
            self._link.baudrate = default_baud
            self._link.connect()

            try:
                self._handshake()
            except links.LinkError as e:
                raise ClientError("could not connect, no response") from e

            log.info("handshake successful, switching to {} baud...".format(max_baud))

            self._write_reg("uart_baudrate", max_baud)
            self._link.disconnect()
            self._link.baudrate = max_baud
            self._link.connect()
            self._handshake()

            log.info("successfully connected at {} baud!".format(max_baud))

        ver = self._read_reg("product_version")
        if ver < protocol.MIN_VERSION:
            log.warn("server version is not supported (too old)")
        elif ver != protocol.DEV_VERSION:
            log.warn("server version might not be fully supported")

    def _setup_session(self, config):
        if len(config.sensor) > 1:
            raise ValueError("the register protocol does not support multiple sensors")
        if config.sensor[0] != 1:
            raise ValueError("the register protocol currently only supports using sensor 1")

        mode = protocol.get_mode(config.mode)
        self._mode = mode

        self._write_reg("main_control", "stop")

        self._write_reg("mode_selection", mode)
        self._write_reg("repetition_mode", "fixed")
        self._write_reg("streaming_control", "uart")

        if mode == "iq":
            self._write_reg("output_data_compression", 1)

        rvs = utils.get_reg_vals_for_config(config)
        for rv in rvs:
            self._write_reg_raw(rv.addr, rv.val)

        self._write_reg("main_control", "create")

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

            if bpp and freq:
                data_rate = 8 * bpp * data_length * freq
                log_text = "data rate: {:.2f} Mbit/s".format(data_rate*1e-6)
                if data_rate > 2/3 * self._link.baudrate:
                    log.warn(log_text)
                    log.warn("data rate might be too high")
                else:
                    log.info(log_text)

        return info

    def _start_streaming(self):
        self._write_reg("main_control", "activate")

    def _get_next(self):
        packet = self._recv_packet(allow_recovery_skip=True)

        if not isinstance(packet, protocol.UnpackedStreamData):
            raise ClientError("got unexpected type of frame")

        info = {}
        for addr, enc_val in packet.result_info:
            try:
                reg = protocol.get_reg(addr, self._mode)
                val = protocol.decode_reg_val(reg, enc_val)
            except protocol.ProtocolError:
                log.info("got unknown reg val in result info")
                log.info("addr: {}, value: {}".format(addr, utils.fmt_enc_val(enc_val)))
            else:
                info[reg.name] = val

        data = protocol.decode_output_buffer(packet.buffer, self._mode, self._num_subsweeps)

        if self.squeeze:
            return info, data
        else:
            return [info], np.expand_dims(data, 0)

    def _stop_streaming(self):
        self._write_reg("main_control", "stop", expect_response=False)

        t0 = time()
        while time() - t0 < self._link._timeout:
            res = self._recv_packet()

            if isinstance(res, protocol.UnpackedRegWriteResponse):
                break
            if not isinstance(res, protocol.UnpackedStreamData):
                raise ClientError("got unexpected packet while stopping session")
        else:
            raise ClientError("timeout while stopping session")

    def _disconnect(self):
        self._link.disconnect()

    def _read_reg(self, reg, mode=None):
        mode = mode or self._mode
        reg = protocol.get_reg(reg, mode)
        enc_val = self._read_reg_raw(reg.addr)
        return protocol.decode_reg_val(reg, enc_val)

    def _read_reg_raw(self, addr):
        addr = protocol.get_addr_for_reg(addr)
        req = protocol.UnpackedRegReadRequest(addr)
        self._send_packet(req)

        log.debug("sent reg r req: addr: {:3}".format(addr))

        res = self._recv_packet()
        if not isinstance(res, protocol.UnpackedRegReadResponse):
            raise ClientError("got unexpected type of frame")

        enc_val = res.reg_val.val

        log.debug("recv reg r res: addr: {:3} val: {}".format(addr, utils.fmt_enc_val(enc_val)))

        return enc_val

    def _write_reg(self, reg, val, expect_response=True):
        reg = protocol.get_reg(reg, self._mode)
        enc_val = protocol.encode_reg_val(reg, val)
        self._write_reg_raw(reg.addr, enc_val, expect_response)

    def _write_reg_raw(self, addr, enc_val, expect_response=True):
        addr = protocol.get_addr_for_reg(addr)
        rrv = protocol.UnpackedRegVal(addr, enc_val)
        req = protocol.UnpackedRegWriteRequest(rrv)
        self._send_packet(req)

        log.debug("sent reg w req: addr: {:3} val: {}".format(addr, utils.fmt_enc_val(enc_val)))

        if expect_response:
            res = self._recv_packet()
            if not isinstance(res, protocol.UnpackedRegWriteResponse):
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

                packet = buf_2[si+1+protocol.LEN_FIELD_SIZE:-1]
                break

            log.warn("successfully recovered from corrupt frame")

        return protocol.unpack_packet(packet)

    def _handshake(self):
        self._write_reg("main_control", "stop", expect_response=False)

        exp_addr = protocol.get_addr_for_reg("main_control")
        exp_enc_val = protocol.encode_reg_val("main_control", "stop")
        exp_reg_val = protocol.UnpackedRegVal(exp_addr, exp_enc_val)
        exp_packet = protocol.UnpackedRegWriteResponse(exp_reg_val)
        exp_frame = protocol.insert_packet_into_frame(exp_packet)
        self._link.recv_until(exp_frame)

        idn_reg = self._read_reg("product_id")
        if idn_reg != protocol.EXPECTED_ID:
            raise ClientError("unexpected product id")


class RegSPIClient(BaseClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._mode = protocol.NO_MODE
        self._proc = None
        self._num_subsweeps = None

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
        if idn_reg != protocol.EXPECTED_ID:
            raise ClientError("unexpected product id")

        ver = self._read_reg("product_version")
        if ver < protocol.MIN_VERSION:
            log.warn("server version is not supported (too old)")
        elif ver != protocol.DEV_VERSION:
            log.warn("server version might not be fully supported")

    def _setup_session(self, config):
        if len(config.sensor) > 1:
            raise ValueError("the register protocol does not support multiple sensors")
        if config.sensor[0] != 1:
            raise ValueError("the register protocol currently only supports using sensor 1")

        mode = protocol.get_mode(config.mode)
        self._mode = mode

        self.__cmd_proc("set_mode_and_rate", mode, config.sweep_rate)

        self._sweep_rate = config.sweep_rate

        self._write_reg("main_control", "stop")

        self._write_reg("mode_selection", mode)
        self._write_reg("repetition_mode", "fixed")
        self._write_reg("streaming_control", "disable")

        if mode == "iq":
            self._write_reg("output_data_compression", 1)

        rvs = utils.get_reg_vals_for_config(config)
        for rv in rvs:
            self._write_reg_raw(rv.addr, rv.val)

        self._write_reg("main_control", "create")
        sleep(SPI_MAIN_CTRL_SLEEP)

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

            if bpp and freq:
                data_rate = 8 * bpp * data_length * freq
                log_text = "data rate: {:.2f} Mbit/s".format(data_rate*1e-6)
                log.info(log_text)

        return info

    def _start_streaming(self):
        self.__cmd_proc("start_streaming")
        self._seq_num = None

    def _get_next(self):
        ret_cmd, ret_args = self._data_queue.get()
        if ret_cmd == "error":
            raise ClientError("exception raised in SPI communcation process")
        elif ret_cmd != "get_next":
            raise ClientError
        info, buffer = ret_args

        data = protocol.decode_output_buffer(buffer, self._mode, self._num_subsweeps)

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

    def _stop_streaming(self):
        self.__cmd_proc("stop_streaming")

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

    def __cmd_proc(self, cmd, *args):
        log.debug("sending cmd to proc: {}".format(cmd))
        self._cmd_queue.put((cmd, args))
        if cmd == "stop_streaming":
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

                if cmd == "start_streaming":
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
            status = self.read_reg("status")
            if not status:
                if (time() - poll_t) > (2/self.sweep_rate + 0.5):
                    raise ClientError("gave up polling")
                continue
            elif status & protocol.STATUS_DATA_READY_MASK:
                break
            elif status & protocol.STATUS_ERROR_MASK:
                self.write_reg("main_control", "clear_status")
                log.info("lost sweep due to server error")
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
            info[reg.name] = self.read_reg(reg)

        self.write_reg("main_control", "clear_status")

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
        self.sweep_rate = sweep_rate
        self.mode = mode

    def start_streaming(self):
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

    def stop_streaming(self):
        self.write_reg("main_control", "stop")

    def disconnect(self):
        self.dev.close()

    def read_reg(self, reg):
        reg = protocol.get_reg(reg, self.mode)
        enc_val = self.read_reg_raw(reg.addr)
        return protocol.decode_reg_val(reg, enc_val)

    def read_reg_raw(self, addr):
        addr = protocol.get_addr_for_reg(addr)
        b = bytearray([protocol.REG_READ_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        enc_val = self.dev.spi_master_single_read(4)
        log.debug("reg r res: addr: {:3} val: {}".format(addr, utils.fmt_enc_val(enc_val)))
        return enc_val

    def write_reg(self, reg, val):
        reg = protocol.get_reg(reg, self.mode)
        enc_val = protocol.encode_reg_val(reg, val)
        self.write_reg_raw(reg.addr, enc_val)

    def write_reg_raw(self, addr, enc_val):
        addr = protocol.get_addr_for_reg(addr)
        b = bytearray([protocol.REG_WRITE_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        log.debug("reg w req: addr: {:3} val: {}".format(addr, utils.fmt_enc_val(enc_val)))
        self.dev.spi_master_single_write(enc_val)

    def read_buf_raw(self, addr, size):
        b = bytearray([protocol.BUF_READ_REQUEST, addr, 0, 0])
        self.dev.spi_master_single_write(b)
        return self.dev.spi_master_single_read(size)
