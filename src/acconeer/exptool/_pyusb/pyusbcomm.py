# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import time

import usb.core
from usb.util import CTRL_RECIPIENT_INTERFACE, CTRL_TYPE_CLASS


DEFAULT_TIMEOUT = 2
USB_PACKET_TIMEOUT_MS = 10
USB_CDC_CMD_SEND_BREAK = 0x23


class UsbPortError(Exception):
    pass


class PyUsbComm:

    device_cache = {}

    def __init__(self):
        pass

    def iterate_devices(self):
        dev = usb.core.find(find_all=True)
        for cfg in dev:
            yield (cfg.idVendor, cfg.idProduct)

    def is_accessible(self, vid, pid):
        vid_pid_str = f"{vid:04x}:{pid:04x}"

        if vid_pid_str in self.device_cache:
            return self.device_cache[vid_pid_str]
        else:
            try:
                device = usb.core.find(idVendor=vid, idProduct=pid)
                # This will raise an USBError exception if inaccessible
                device.is_kernel_driver_active(0)
                self.device_cache[vid_pid_str] = True
            except usb.core.USBError:
                self.device_cache[vid_pid_str] = False

        return self.device_cache[vid_pid_str]


class PyUsbCdc:
    def __init__(self, name=None, vid=None, pid=None, start=True):
        self.vid = vid
        self.pid = pid
        self._timeout = DEFAULT_TIMEOUT
        self._dev = None
        self._cdc_data_out_ep = None
        self._cdc_data_in_ep = None
        self.is_open = False
        self._rxremaining = b""

        if name:
            raise AttributeError("PyUsbCdc can only be accessed with vid & pid")

        if not (vid and pid):
            raise AttributeError("Must provide vid & pid of device to connect to")

        if start:
            self.open()

    def open(self):
        self._dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)

        try:
            self._dev.reset()
        except usb.core.USBError:
            raise UsbPortError("Could not access USB device")

        # Detach kernel driver
        if self._dev.is_kernel_driver_active(0):
            self._dev.detach_kernel_driver(0)

        # The XC120 USB device only has one config
        config = self._dev[0]

        # Interface 1 is the CDC Data interface
        iface1 = config.interfaces()[1]
        # Interface 0 has one Endpoint for data out and one Endpoint for data in
        self._cdc_data_out_ep = iface1.endpoints()[0]
        self._cdc_data_in_ep = iface1.endpoints()[1]

        self.is_open = True

        self.reset_input_buffer()

        return True

    @property
    def timeout(self):
        return self._timeout

    def settimeout(self, timeout):
        self._timeout = timeout

    @timeout.setter
    def timeout(self, timeout):
        self.settimeout(timeout)

    def read(self, size=None):
        if not self.is_open:
            raise UsbPortError("Port is not open")

        rx = [self._rxremaining]
        length = len(self._rxremaining)
        self._rxremaining = b""
        end_timeout = time.time() + (self.timeout or 0.2)
        if size:
            while length < size:
                c = self._dev.read(
                    self._cdc_data_in_ep.bEndpointAddress, self._cdc_data_in_ep.wMaxPacketSize
                )
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                if time.time() > end_timeout:
                    break
        else:
            while True:
                c = None
                try:
                    c = self._dev.read(
                        self._cdc_data_in_ep.bEndpointAddress,
                        self._cdc_data_in_ep.wMaxPacketSize,
                        timeout=USB_PACKET_TIMEOUT_MS,
                    )
                except usb.core.USBTimeoutError:
                    pass
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
            raise UsbPortError("Port is not open")
        self._dev.write(self._cdc_data_out_ep, data)

    def reset_input_buffer(self):
        self._rxremaining = b""

    def send_break(self, duration=0.25):
        if not self.is_open:
            raise UsbPortError("Port is not open")
        self._dev.ctrl_transfer(
            CTRL_TYPE_CLASS | CTRL_RECIPIENT_INTERFACE,
            USB_CDC_CMD_SEND_BREAK,
            wValue=0xFFFF,
            wIndex=0,
        )

    def disconnect(self):
        if self.is_open:
            self._dev.reset()
            self._dev.attach_kernel_driver(0)
            self.is_open = False

    def __del__(self):
        self.disconnect()

    def close(self):
        self.disconnect()
