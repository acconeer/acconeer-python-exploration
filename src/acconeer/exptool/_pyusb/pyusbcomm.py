# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import time

import usb.core
from usb.util import CTRL_RECIPIENT_INTERFACE, CTRL_TYPE_CLASS


class UsbPortError(Exception):
    pass


class PyUsbComm:

    device_cache = {}

    def __init__(self):
        pass

    def iterate_devices(self):
        dev = usb.core.find(find_all=True)
        for cfg in dev:
            serial_number = None
            try:
                serial_number = cfg.serial_number
            except ValueError:
                pass
            yield (cfg.idVendor, cfg.idProduct, serial_number)

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

    USB_CDC_CMD_SEND_BREAK = 0x23
    USB_MESSAGE_TIMEOUT = 2
    USB_MESSAGE_TIMEOUT_MS = 1000 * USB_MESSAGE_TIMEOUT
    USB_PACKET_TIMEOUT_MS = 200

    def __init__(self, vid=None, pid=None, serial=None, start=True):
        self.serial = serial
        self.vid = vid
        self.pid = pid
        self._dev = None
        self._cdc_data_out_ep = None
        self._cdc_data_in_ep = None
        self.is_open = False
        self._rxremaining = b""

        if not (vid and pid):
            raise AttributeError("Must provide vid & pid of device to connect to")

        if start:
            self.open()

    def open(self):
        def match(dev):
            if self.vid == dev.idVendor and self.pid == dev.idProduct:
                if self.serial is not None:
                    try:
                        serial_number = dev.serial_number
                    except ValueError:
                        pass
                    if serial_number and serial_number == self.serial:
                        return True
                else:
                    return True
            return False

        self._dev = usb.core.find(custom_match=match)

        # Detach kernel driver
        try:
            if self._dev.is_kernel_driver_active(0):
                self._dev.detach_kernel_driver(0)
        except usb.core.USBError:
            raise UsbPortError("Could not access USB device")

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

    def read(self, size=None):
        if not self.is_open:
            raise UsbPortError("Port is not open")

        rx = [self._rxremaining]
        length = len(self._rxremaining)
        self._rxremaining = b""
        end_timeout = time.monotonic() + self.USB_MESSAGE_TIMEOUT
        if size:
            while length < size:
                try:
                    c = self._dev.read(
                        self._cdc_data_in_ep.bEndpointAddress,
                        self._cdc_data_in_ep.wMaxPacketSize,
                        timeout=self.USB_PACKET_TIMEOUT_MS,
                    )
                except usb.core.USBTimeoutError:
                    pass
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                if time.monotonic() > end_timeout:
                    break
        else:
            c = None
            try:
                c = self._dev.read(
                    self._cdc_data_in_ep.bEndpointAddress,
                    self._cdc_data_in_ep.wMaxPacketSize,
                    timeout=self.USB_MESSAGE_TIMEOUT_MS,
                )
            except usb.core.USBTimeoutError:
                pass
            if c is not None and len(c):
                rx.append(c)
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
            self.USB_CDC_CMD_SEND_BREAK,
            wValue=0xFFFF,
            wIndex=0,
        )

    def disconnect(self):
        if self.is_open:
            try:
                usb.util.dispose_resources(self._dev)
                self._dev.attach_kernel_driver(0)
            except usb.core.USBError:
                pass
            self._dev = None
            self.is_open = False

    def __del__(self):
        self.disconnect()

    def close(self):
        self.disconnect()
