import numpy as np
import logging
from time import time

from acconeer_utils.clients.base import BaseClient, ClientError
from acconeer_utils.clients.reg import protocol, utils
from acconeer_utils.clients import links


log = logging.getLogger(__name__)


class RegClient(BaseClient):
    def __init__(self, port, **kwargs):
        super().__init__(**kwargs)

        self._link = links.SerialProcessLink(port)

        self._mode = protocol.NO_MODE

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
                log.info("addr: {}, value: {}".format(addr, self._fmt_enc_val(enc_val)))
            else:
                info[reg.name] = val

        data = protocol.decode_output_buffer(packet.buffer, self._mode)

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

        log.debug("recv reg r res: addr: {:3} val: {}".format(addr, self._fmt_enc_val(enc_val)))

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

        log.debug("sent reg w req: addr: {:3} val: {}".format(addr, self._fmt_enc_val(enc_val)))

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

    def _fmt_enc_val(self, enc_val):
        return " ".join(["{:02x}".format(x) for x in enc_val])
