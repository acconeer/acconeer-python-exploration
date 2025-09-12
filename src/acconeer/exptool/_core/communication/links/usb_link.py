# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
from __future__ import annotations

import contextlib
import pathlib
import platform
import sys
import time
from typing import Any, Optional

import libusb
import usb.backend.libusb1
import usb.core
from usb.util import CTRL_RECIPIENT_INTERFACE, CTRL_TYPE_CLASS

from .buffered_link import BufferedLink, LinkError


def get_libusb_backend() -> Any:
    """Helper function to setup libusb backend"""
    backend = None
    if platform.system().lower() in ["windows"]:
        win_arch = "x64" if sys.maxsize > 2**32 else "x86"
        libusb_dll_path = (
            pathlib.Path(libusb.__file__).parent
            / "_platform"
            / "_windows"
            / win_arch
            / "libusb-1.0.dll"
        )
        backend = usb.backend.libusb1.get_backend(find_library=lambda x: str(libusb_dll_path))
    return backend


class UsbPortError(Exception):
    pass


class PyUsbCdc:
    USB_CDC_CMD_SEND_BREAK = 0x23
    USB_MESSAGE_TIMEOUT = 2
    USB_MESSAGE_TIMEOUT_MS = 1000 * USB_MESSAGE_TIMEOUT
    USB_PACKET_TIMEOUT_MS = 200

    def __init__(
        self,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
        serial: Optional[str] = None,
        start: bool = True,
    ) -> None:
        self.serial = serial
        self.vid = vid
        self.pid = pid
        self._dev = None
        self._cdc_data_out_ep = None
        self._cdc_data_in_ep = None
        self._rxremaining = b""
        self._backend = get_libusb_backend()

        if not (vid and pid):
            msg = "Must provide vid & pid of device to connect to"
            raise AttributeError(msg)

        if start:
            self.open()

    def open(self) -> bool:
        def match(dev: usb.core.Device) -> bool:
            if self.vid == dev.idVendor and self.pid == dev.idProduct:
                if self.serial is not None:
                    with contextlib.suppress(ValueError):
                        serial_number = dev.serial_number
                        if serial_number and serial_number == self.serial:
                            return True
                else:
                    return True
            return False

        self._dev = usb.core.find(custom_match=match, backend=self._backend)

        # Detach kernel driver
        if self._dev is None:
            msg = "Port is not open"
            raise UsbPortError(msg)
        try:
            if self._dev.is_kernel_driver_active(0):
                self._dev.detach_kernel_driver(0)
        except usb.core.USBError:
            msg = "Could not access USB device, are USB permissions setup correctly?"
            raise UsbPortError(msg)
        except NotImplementedError:
            # The function is_kernel_driver_active is not implemented in windows libusb
            pass

        # The Acconeer USB device descriptor only has one config
        config = self._dev[0]

        # Interface 1 is the CDC Data interface
        iface1 = config.interfaces()[1]
        # Interface 0 has one Endpoint for data out and one Endpoint for data in
        self._cdc_data_out_ep = iface1.endpoints()[0]
        self._cdc_data_in_ep = iface1.endpoints()[1]

        return True

    def read(self, size: Optional[int] = None) -> list[int]:
        if self._dev is None:
            msg = "Port is not open"
            raise UsbPortError(msg)

        rx = [self._rxremaining]
        length = len(self._rxremaining)
        self._rxremaining = b""
        end_timeout = time.monotonic() + self.USB_MESSAGE_TIMEOUT
        if size is not None:
            while length < size:
                with contextlib.suppress(usb.core.USBTimeoutError):
                    c = self._dev.read(
                        self._cdc_data_in_ep.bEndpointAddress,
                        self._cdc_data_in_ep.wMaxPacketSize,
                        timeout=self.USB_PACKET_TIMEOUT_MS,
                    )
                if c is not None and len(c):
                    rx.append(c)
                    length += len(c)
                if time.monotonic() > end_timeout:
                    break
        else:
            c = None
            with contextlib.suppress(usb.core.USBTimeoutError):
                c = self._dev.read(
                    self._cdc_data_in_ep.bEndpointAddress,
                    self._cdc_data_in_ep.wMaxPacketSize,
                    timeout=self.USB_MESSAGE_TIMEOUT_MS,
                )
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

    def write(self, data: bytes) -> None:
        if self._dev is None:
            msg = "Port is not open"
            raise UsbPortError(msg)
        self._dev.write(self._cdc_data_out_ep, data)

    def reset_input_buffer(self) -> None:
        if self._dev is None:
            msg = "Port is not open"
            raise UsbPortError(msg)

        self._rxremaining = b""
        while True:
            try:
                self._dev.read(
                    self._cdc_data_in_ep.bEndpointAddress,
                    self._cdc_data_in_ep.wMaxPacketSize,
                    timeout=self.USB_PACKET_TIMEOUT_MS,
                )
            except usb.core.USBTimeoutError:
                break

    def send_break(self, duration: float = 0.25) -> None:
        if self._dev is None:
            msg = "Port is not open"
            raise UsbPortError(msg)
        self._dev.ctrl_transfer(
            CTRL_TYPE_CLASS | CTRL_RECIPIENT_INTERFACE,
            self.USB_CDC_CMD_SEND_BREAK,
            wValue=0xFFFF,
            wIndex=0,
        )

    def disconnect(self) -> None:
        if self._dev is not None:
            try:
                usb.util.dispose_resources(self._dev)
                self._dev.attach_kernel_driver(0)
            except usb.core.USBError:
                pass
            except NotImplementedError:
                # The function attach_kernel_driver is not implemented in windows libusb
                pass

            self._dev = None

    def __del__(self) -> None:
        self.disconnect()

    def close(self) -> None:
        self.disconnect()


class USBLink(BufferedLink):
    def __init__(
        self, vid: Optional[int] = None, pid: Optional[int] = None, serial: Optional[str] = None
    ) -> None:
        super().__init__()
        self._vid = vid
        self._pid = pid
        self._serial = serial
        self._port: Optional[PyUsbCdc] = None

    def _update_timeout(self) -> None:
        # timeout is manually handled in recv/recv_until
        pass

    def connect(self) -> None:
        if self._vid and self._pid:
            self._port = PyUsbCdc(vid=self._vid, pid=self._pid, serial=self._serial, start=False)
        else:
            msg = "Must have vid and pid for usb device"
            raise LinkError(msg)

        if not self._port.open():
            msg = f"Unable to connect to port (vid={self._vid}, pid={self._pid}"
            raise LinkError(msg)

        self._buf = bytearray()
        self.send_break()

    def send_break(self) -> None:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        self._port.send_break()
        time.sleep(1.0)
        self._port.reset_input_buffer()

    def recv(self, num_bytes: int) -> bytes:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        t0 = time.time()
        while len(self._buf) < num_bytes:
            if time.time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

            try:
                r = bytearray(self._port.read())
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        data = self._buf[:num_bytes]
        self._buf = self._buf[num_bytes:]
        return data

    def recv_until(self, bs: bytes) -> bytes:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        t0 = time.time()
        while True:
            try:
                i = self._buf.index(bs)
            except ValueError:
                pass
            else:
                break

            if time.time() - t0 > self._timeout:
                msg = "recv timeout"
                raise LinkError(msg)

            try:
                r = bytearray(self._port.read())
            except OSError as e:
                raise LinkError from e
            self._buf.extend(r)

        i += 1
        data = self._buf[:i]
        self._buf = self._buf[i:]

        return data

    def send(self, data: bytes) -> None:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)
        self._port.write(data)

    def disconnect(self) -> None:
        if self._port is not None:
            self._port.close()
            self._port = None
