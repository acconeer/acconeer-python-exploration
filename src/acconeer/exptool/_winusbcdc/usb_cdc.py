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
    def __init__(self, serial=None, vid=None, pid=None, start=True):
        self.serial = serial
        self.vid = vid
        self.pid = pid

        if not (vid and pid):
            raise AttributeError("Must provide vid & pid of device to connect to")

        self.winusbpy = WinUsbPy()
        self._rxremaining = b""
        self.maximum_packet_size = 0
        self.timeout = 0.01
        self.is_open = False
        if start:
            self.open()

    def open(self):
        # Control interface
        device_list = self.winusbpy.find_all_devices()
        device_path = None
        for device in device_list:
            if self.vid == device["vid"] and self.pid == device["pid"]:
                if self.serial is not None:
                    if self.serial == device["serial"]:
                        device_path = device["path"]
                        break
                else:
                    device_path = device["path"]
                    break
        if device_path is None:
            return False

        if not self.winusbpy.init_winusb_device(device_path):
            return False

        # Data Interface
        self.winusbpy.change_interface(0)
        interface2_descriptor = self.winusbpy.query_interface_settings(0)

        pipe_info_list = map(
            self.winusbpy.query_pipe, range(interface2_descriptor.b_num_endpoints)
        )
        for item in pipe_info_list:
            if item.pipe_id & 0x80:
                self._ep_in = item.pipe_id
            else:
                self._ep_out = item.pipe_id
            self.maximum_packet_size = (
                min(item.maximum_packet_size, self.maximum_packet_size) or item.maximum_packet_size
            )

        self.is_open = True

        self.winusbpy.set_timeout(self._ep_in, self.timeout)
        self.reset_input_buffer()
        return True

    def read(self, size=None):
        if not self.is_open:
            return None
        rx = [self._rxremaining]
        length = len(self._rxremaining)
        self._rxremaining = b""
        end_timeout = time.monotonic() + (self.timeout or 0.2)
        if size:
            while length < size:
                c = self.winusby.read(self._ep_in, size - length)
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                if time.monotonic() > end_timeout:
                    break
        else:
            while True:
                c = self.winusbpy.read(self._ep_in, self.maximum_packet_size)
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                else:
                    break
                if time.monotonic() > end_timeout:
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
            ret = self.winusbpy.write(self._ep_out, data)
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

        wlen = self.winusbpy.control_transfer(pkt, buff)
        log.debug("Send break, {}b sent".format(wlen))

    def disconnect(self):
        if not self.is_open:
            return None
        self.winusbpy.close_winusb_device()
        self.is_open = False

    def __del__(self):
        self.disconnect()

    def reset_input_buffer(self):
        if self.is_open:
            self.winusbpy.flush(self._ep_in)
            while self.read():
                pass
        self._rxremaining = b""

    def flush(self):
        if not self.is_open:
            return None
        self.winusbpy.flush(self._ep_in)

    def close(self):
        self.disconnect()
