#!/usr/bin/env python
"""
VIRTUAL COM PORT TERMINAL
- implements a read/write terminal for communicating
with USB CDC device on winusb driver

SERIAL STATE notifications (2 bytes, interrupt endpoint)
    15..7 - reserved
    6   bOverRun    Received data has been discarded due to a device overrun
    5   bParity     A parity error has occurred
    4   bFraming    A framing error has occurred
    3   bRingSignal State of the ring indicator (RI)
    2   bBreak      Break state
    1   bTxCarrier  State of the data set ready (DSR)
    0   bRxCarrier  State of carrier detect (CD)

Line Coding Data Field (7 bytes, control endpoint)
    offset field       (bytes) Description
    --------------------------------------------------------------------
    0      dwDTERate   4       bit rate (bits per second)
    4      bCharFormat 1       stop bits (0 : 1bit, 1, 1.5bits, 2, 2bits)
    5      bParityType 1       0:None, 1:Odd, 2:Even, 3:Mark, 4:Space
    6      bDataBits   1       5, 6, 7, 8, 16

Control Line State Field (2 bytes, control endpoint)
    wValueBit  Description     (2 bytes data)
    ---------------------------
    bit 1 = 0  RTS : de-assert (negative voltage)
    bit 1 = 1  RTS : assert    (positive voltage)
    bit 0 = 0  DTR : de-assert (negative voltage)
    bit 0 = 1  DTR : assert    (positive voltage)

"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import time

from .winusbclasses import UsbSetupPacket
from .winusbpy import WinUsbPy


CDC_CMDS = {
    "SEND_ENCAPSULATED_COMMAND": 0x00,
    "GET_ENCAPSULATED_RESPONSE": 0x01,
    "SET_COMM_FEATURE": 0x02,
    "GET_COMM_FEATURE": 0x03,
    "CLEAR_COMM_FEATURE": 0x04,
    "SET_LINE_CODING": 0x20,
    "GET_LINE_CODING": 0x21,
    "SET_CONTROL_LINE_STATE": 0x22,
    "SEND_BREAK": 0x23,  # wValue is break time
}


def config_log():
    log = logging.getLogger("usb_cdc")
    if "PYTERMINAL_DEBUG" in os.environ:
        log.setLevel(logging.DEBUG)
        fileHandler = logging.FileHandler("terminal.log")
        log_fmt = logging.Formatter(
            "%(levelname)s %(name)s %(threadName)-10s " + "%(funcName)s() %(message)s"
        )
        fileHandler.setFormatter(log_fmt)
        log.addHandler(fileHandler)
    return log


log = config_log()


class ComPort:
    def __init__(self, name=None, vid=None, pid=None, start=True):
        self.name = name
        self.vid = vid
        self.pid = pid
        if not name and not (vid and pid):
            raise AttributeError(
                "Must provide friendly name _or_ vid & pid of device to connect to"
            )
        if name and (vid or pid):
            raise AttributeError(
                "Must provide friendly name _or_ vid & pid of device to connect to"
            )

        self.device = None
        self._rxremaining = b""
        self.baudrate = 9600
        self.parity = 0
        self.stopbits = 1
        self.databits = 8
        self.maximum_packet_size = 0

        self.timeout = 0.01

        self.is_open = False
        if start:
            self.open()

    def open(self):
        # Control interface
        api = self._select_device(self.name, self.vid, self.pid)
        if not api:
            return False

        # interface_descriptor = api.query_interface_settings(0)
        # pipe_info_list = map(api.query_pipe, range(interface_descriptor.b_num_endpoints))

        # Data Interface
        api.change_interface(0)
        interface2_descriptor = api.query_interface_settings(0)

        pipe_info_list = map(api.query_pipe, range(interface2_descriptor.b_num_endpoints))
        for item in pipe_info_list:
            if item.pipe_id & 0x80:
                self._ep_in = item.pipe_id
            else:
                self._ep_out = item.pipe_id
            self.maximum_packet_size = (
                min(item.maximum_packet_size, self.maximum_packet_size) or item.maximum_packet_size
            )

        self.device = api  # type: WinUsbPy

        self.is_open = True

        self.setControlLineState(True, True)
        self.setLineCoding()
        self.device.set_timeout(self._ep_in, self.timeout)
        self.reset_input_buffer()
        return True

    @property
    def in_waiting(self):
        return False

    def read(self, size=None):
        if not self.is_open:
            return None
        rx = [self._rxremaining]
        length = len(self._rxremaining)
        self._rxremaining = b""
        end_timeout = time.time() + (self.timeout or 0.2)
        if size:
            while length < size:
                c = self.device.read(self._ep_in, size - length)
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                if time.time() > end_timeout:
                    break
        else:
            while True:
                c = self.device.read(self._ep_in, self.maximum_packet_size)
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                else:
                    break
                if time.time() > end_timeout:
                    break
        chunk = b"".join(rx)
        if size and len(chunk) >= size:
            if self._rxremaining:
                self._rxremaining = chunk[size:] + self._rxremaining
            else:
                self._rxremaining = chunk[size:]
            chunk = chunk[0:size]
        return chunk

    def write(self, data):
        if not self.is_open:
            return None
        try:
            ret = self.device.write(self._ep_out, data)
        except Exception as e:
            log.warning("USB Error on write {}".format(e))
            return

        if len(data) != ret:
            log.error("Bytes written mismatch {0} vs {1}".format(len(data), ret))
        else:
            log.debug("{} bytes written to ep".format(ret))

    def send_break(self, duration=0.25):
        if not self.is_open:
            return None

        duration_s = int(duration * 1000)

        txdir = 0  # 0:OUT, 1:IN
        req_type = 1  # 0:std, 1:class, 2:vendor
        # 0:device, 1:interface, 2:endpoint, 3:other
        recipient = 1
        req_type = (txdir << 7) + (req_type << 5) + recipient

        pkt = UsbSetupPacket(
            request_type=req_type,
            request=CDC_CMDS["SEND_BREAK"],
            value=duration_s,
            index=0x00,
            length=0x00,
        )

        buff = None

        wlen = self.device.control_transfer(pkt, buff)
        log.debug("Send break, {}b sent".format(wlen))

    def setControlLineState(self, RTS=None, DTR=None):
        if not self.is_open:
            return None
        ctrlstate = (2 if RTS else 0) + (1 if DTR else 0)

        txdir = 0  # 0:OUT, 1:IN
        req_type = 1  # 0:std, 1:class, 2:vendor
        # 0:device, 1:interface, 2:endpoint, 3:other
        recipient = 1
        req_type = (txdir << 7) + (req_type << 5) + recipient

        pkt = UsbSetupPacket(
            request_type=req_type,
            request=CDC_CMDS["SET_CONTROL_LINE_STATE"],
            value=ctrlstate,
            index=0x00,
            length=0x00,
        )
        # buff = [0xc0, 0x12, 0x00, 0x00, 0x00, 0x00, 0x08]
        buff = None

        wlen = self.device.control_transfer(pkt, buff)
        log.debug("Linecoding set, {}b sent".format(wlen))

    def setLineCoding(self, baudrate=None, parity=None, databits=None, stopbits=None):
        if not self.is_open:
            return None
        sbits = {1: 0, 1.5: 1, 2: 2}
        dbits = {5, 6, 7, 8, 16}
        pmodes = {0, 1, 2, 3, 4}
        brates = {
            300,
            600,
            1200,
            2400,
            4800,
            9600,
            14400,
            19200,
            28800,
            38400,
            57600,
            115200,
            230400,
        }

        if stopbits is not None:
            if stopbits not in sbits.keys():
                valid = ", ".join(str(k) for k in sorted(sbits.keys()))
                raise ValueError("Valid stopbits are " + valid)
            self.stopbits = stopbits

        if databits is not None:
            if databits not in dbits:
                valid = ", ".join(str(d) for d in sorted(dbits))
                raise ValueError("Valid databits are " + valid)
            self.databits = databits

        if parity is not None:
            if parity not in pmodes:
                valid = ", ".join(str(pm) for pm in sorted(pmodes))
                raise ValueError("Valid parity modes are " + valid)
            self.parity = parity

        if baudrate is not None:
            if baudrate not in brates:
                brs = sorted(brates)
                dif = [abs(br - baudrate) for br in brs]
                best = brs[dif.index(min(dif))]
                raise ValueError("Invalid baudrates, nearest valid is {}".format(best))
            self.baudrate = baudrate

        linecode = [
            self.baudrate & 0xFF,
            (self.baudrate >> 8) & 0xFF,
            (self.baudrate >> 16) & 0xFF,
            (self.baudrate >> 24) & 0xFF,
            sbits[self.stopbits],
            self.parity,
            self.databits,
        ]

        txdir = 0  # 0:OUT, 1:IN
        req_type = 1  # 0:std, 1:class, 2:vendor
        recipient = 1  # 0:device, 1:interface, 2:endpoint, 3:other
        req_type = (txdir << 7) + (req_type << 5) + recipient

        pkt = UsbSetupPacket(
            request_type=req_type,
            request=CDC_CMDS["SET_LINE_CODING"],
            value=0x0000,
            index=0x00,
            length=len(linecode),
        )
        # buff = [0xc0, 0x12, 0x00, 0x00, 0x00, 0x00, 0x08]
        buff = linecode

        wlen = self.device.control_transfer(pkt, buff)
        # req_type, CDC_CMDS["SET_LINE_CODING"],
        # data_or_wLength=linecode)
        log.debug("Linecoding set, {}b sent".format(wlen))

    # def getLineCoding(self):
    #     txdir = 1           # 0:OUT, 1:IN
    #     req_type = 1        # 0:std, 1:class, 2:vendor
    #     recipient = 1       # 0:device, 1:interface, 2:endpoint, 3:other
    #     req_type = (txdir << 7) + (req_type << 5) + recipient
    #
    #     buf = self.device.ctrl_transfer(bmRequestType=req_type,
    #                                     bRequest=CDC_CMDS["GET_LINE_CODING"],
    #                                     wValue=0,
    #                                     wIndex=0,
    #                                     data_or_wLength=255,
    #                                     )
    #     self.baudrate = buf[0] + (buf[1] << 8) + \
    #         (buf[2] << 16) + (buf[3] << 24)
    #     self.stopbits = 1 + (buf[4] / 2.0)
    #     self.parity = buf[5]
    #     self.databits = buf[6]
    #     print("LINE CODING:")
    #     print("  {0} baud, parity mode {1}".format(self.baudrate, self.parity))
    #     print(
    #         "  {0} data bits, {1} stop bits".format(
    #             self.databits,
    #             self.stopbits))

    def disconnect(self):
        if not self.is_open:
            return None
        self.device.close_winusb_device()
        self.is_open = False

    def __del__(self):
        self.disconnect()

    def reset_input_buffer(self):
        if self.is_open:
            self.device.flush(self._ep_in)
            while self.read():
                pass
        self._rxremaining = b""

    def reset_output_buffer(self):
        pass

    def flush(self):
        if not self.is_open:
            return None
        self.device.flush(self._ep_in)

    def close(self):
        self.disconnect()

    def _select_device(self, name, vid, pid):
        api = WinUsbPy()
        devices = api.list_usb_devices(
            deviceinterface=True, present=True, vid=vid, pid=pid, name=name
        )

        if not devices:
            log.warning("No devices detected")
            return None

        if not api.init_winusb_device(name, vid, pid):
            return None

        return api
