# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import atexit
import contextlib
import ctypes
import os
import sys
import threading
import time
from typing import Any

import libusb_package
import usb.core
import usb1
from usb.util import CTRL_RECIPIENT_INTERFACE, CTRL_TYPE_CLASS

from .buffered_link import BufferedLink, LinkError


# Set to 1 to use LegacyUSBLink for USB devices, for when USBLink causes problems
LEGACY_USB_ENV = "ET_LEGACY_USB"


def legacy_usb_requested() -> bool:
    return os.environ.get(LEGACY_USB_ENV, "") not in ("", "0")


def get_libusb_backend() -> Any:
    """Helper function to setup libusb backend"""
    return libusb_package.get_libusb1_backend()


def load_usb1_library() -> None:
    """Make usb1 use the libusb build from libusb_package, the one pyusb uses.

    usb1 loads libusb with the stdcall convention on Windows, so the same loader is used here.
    Only the first load in a process takes effect.
    """
    path = str(libusb_package.get_library_path())
    if sys.platform == "win32":
        usb1.loadLibrary(ctypes.WinDLL(path))
    else:
        usb1.loadLibrary(ctypes.CDLL(path))


def get_libusb_bulk_interface(dev: usb.core.Device) -> usb.core.Interface | None:
    """
    Helper function to find vendor specific USB interfaces with 2 endpoints
    """
    USB_INTERFACE_CLASS_VENDOR_SPECIFIC = 0xFF
    USB_INTERFACE_NUMBER_OF_ENDPOINTS = 2

    selected_interface = None
    config = dev[0]
    for interface in config.interfaces():
        if (
            interface.bInterfaceClass == USB_INTERFACE_CLASS_VENDOR_SPECIFIC
            and interface.bNumEndpoints == USB_INTERFACE_NUMBER_OF_ENDPOINTS
        ):
            selected_interface = interface
            break

    return selected_interface


class UsbPortError(Exception):
    pass


class PyUsbCdc:
    USB_CDC_CMD_SEND_BREAK = 0x23
    USB_MESSAGE_TIMEOUT = 2
    USB_MESSAGE_TIMEOUT_MS = 1000 * USB_MESSAGE_TIMEOUT
    USB_PACKET_TIMEOUT_MS = 200

    def __init__(
        self,
        vid: int | None = None,
        pid: int | None = None,
        serial: str | None = None,
        start: bool = True,
    ) -> None:
        self.serial = serial
        self.vid = vid
        self.pid = pid
        self._dev = None
        self._iface = None
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

        if self._dev is None:
            msg = "Port is not open"
            raise UsbPortError(msg)
        try:
            self._dev.reset()
        except usb.core.USBError:
            msg = "Could not access USB device, are USB permissions setup correctly?"
            raise UsbPortError(msg)

        self._iface = get_libusb_bulk_interface(self._dev)

        if self._iface is None:
            msg = "Could not find USB device interface"
            raise UsbPortError(msg)

        # Interface should have one Endpoint for data out and one Endpoint for data in
        for endpoint in self._iface.endpoints():
            if usb.util.endpoint_type(endpoint.bmAttributes) != usb.util.ENDPOINT_TYPE_BULK:
                continue
            if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN:
                self._cdc_data_in_ep = endpoint
            else:
                self._cdc_data_out_ep = endpoint

        if self._cdc_data_in_ep is None or self._cdc_data_out_ep is None:
            msg = "Could not find all necessary USB device endpoints"
            raise UsbPortError(msg)

        try:
            usb.util.claim_interface(self._dev, self._iface.bInterfaceNumber)
        except usb.core.USBError:
            msg = "Could not claim USB device interface, is somebody else using it?"
            raise UsbPortError(msg)

        return True

    def read(self, size: int | None = None) -> list[int]:
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
        if self._iface is not None:
            try:
                usb.util.release_interface(self._dev, self._iface.bInterfaceNumber)
                self._iface = None
            except (usb.core.USBError, AttributeError):
                pass
        if self._dev is not None:
            try:
                usb.util.dispose_resources(self._dev)
            except usb.core.USBError:
                pass

            self._dev = None

    def __del__(self) -> None:
        self.disconnect()

    def close(self) -> None:
        self.disconnect()


class AsyncUsbBulk:
    """Vendor bulk interface that keeps reading while the caller is busy.

    An event thread keeps several bulk IN transfers queued in the OS USB driver at all times
    and collects what they receive in a buffer, which the read methods take from. Reading
    only when the caller asks would leave nothing queued while the caller, or the whole
    process, is busy. The device then has to buffer the data itself, and a sensor streaming
    through it has to wait once that buffer is full.
    """

    # Enough queued reads to cover the host not reading for a couple of seconds. A read of at
    # most 16 KiB is one TRB in an xHCI ring. Cancelling a larger one on close can leave the
    # bulk IN endpoint dead until a USB reset on a Raspberry Pi 4 with kernel 6.18.
    TRANSFER_COUNT = 64
    TRANSFER_SIZE = 16 * 1024
    # Stop queueing reads above this, so that a caller that stops reading makes the device
    # wait instead of the buffer growing without end
    MAX_BUFFERED = 64 * 1024 * 1024
    EVENT_TIMEOUT_S = 0.1
    CLOSE_TIMEOUT_S = 2.0
    CONTROL_TIMEOUT_MS = 1000
    WRITE_TIMEOUT_MS = 1000
    USB_CDC_CMD_SEND_BREAK = 0x23
    USB_INTERFACE_CLASS_VENDOR_SPECIFIC = 0xFF
    USB_INTERFACE_NUMBER_OF_ENDPOINTS = 2

    def __init__(self, vid: int, pid: int, serial: str | None = None) -> None:
        self._vid = vid
        self._pid = pid
        self._serial = serial
        self._context: usb1.USBContext | None = None
        self._handle: usb1.USBDeviceHandle | None = None
        self._interface_number: int | None = None
        self._ep_in = 0
        self._ep_out = 0
        self._transfers: list[usb1.USBTransfer] = []
        self._parked: list[usb1.USBTransfer] = []
        self._rx = bytearray()
        self._rx_condition = threading.Condition()
        self._error: Exception | None = None
        self._running = False
        self._event_thread: threading.Thread | None = None
        # When the event thread started its last finished collection of completed reads
        self._polled_at = 0.0

    def open(self) -> None:
        load_usb1_library()
        self._context = usb1.USBContext()
        self._context.open()
        try:
            self._open_device()
            self._start_reading()
        except BaseException:
            self.close()
            raise
        # Stop the event thread before usb1's own exit-time cleanup, which otherwise waits
        # for events the thread takes from it
        atexit.register(self.close)

    def _open_device(self) -> None:
        assert self._context is not None

        for device in self._context.getDeviceIterator(skip_on_error=True):
            if device.getVendorID() != self._vid or device.getProductID() != self._pid:
                continue
            try:
                handle = device.open()
            except usb1.USBError:
                msg = "Could not access USB device, are USB permissions setup correctly?"
                raise UsbPortError(msg)
            if self._serial is not None:
                try:
                    serial = handle.getSerialNumber()
                except usb1.USBError:
                    serial = None
                if serial != self._serial:
                    handle.close()
                    continue
            self._handle = handle
            break

        if self._handle is None:
            msg = "Port is not open"
            raise UsbPortError(msg)

        try:
            self._handle.resetDevice()
        except usb1.USBError:
            msg = "Could not access USB device, are USB permissions setup correctly?"
            raise UsbPortError(msg)

        self._find_bulk_interface()

        try:
            self._handle.claimInterface(self._interface_number)
        except usb1.USBError:
            msg = "Could not claim USB device interface, is somebody else using it?"
            raise UsbPortError(msg)

    def _find_bulk_interface(self) -> None:
        """Find the vendor specific interface with one bulk IN and one bulk OUT endpoint"""
        assert self._handle is not None

        configuration = next(iter(self._handle.getDevice().iterConfigurations()))
        for interface in configuration:
            setting = interface[0]
            if (
                setting.getClass() == self.USB_INTERFACE_CLASS_VENDOR_SPECIFIC
                and setting.getNumEndpoints() == self.USB_INTERFACE_NUMBER_OF_ENDPOINTS
            ):
                break
        else:
            msg = "Could not find USB device interface"
            raise UsbPortError(msg)

        ep_in = ep_out = None
        for endpoint in setting:
            if endpoint.getAttributes() & usb1.TRANSFER_TYPE_MASK != usb1.TRANSFER_TYPE_BULK:
                continue
            address = endpoint.getAddress()
            if address & usb1.ENDPOINT_DIR_MASK == usb1.ENDPOINT_IN:
                ep_in = address
            else:
                ep_out = address

        if ep_in is None or ep_out is None:
            msg = "Could not find all necessary USB device endpoints"
            raise UsbPortError(msg)

        self._interface_number = setting.getNumber()
        self._ep_in = ep_in
        self._ep_out = ep_out

    def _start_reading(self) -> None:
        assert self._handle is not None

        self._running = True
        for _ in range(self.TRANSFER_COUNT):
            transfer = self._handle.getTransfer()
            transfer.setBulk(self._ep_in, self.TRANSFER_SIZE, callback=self._on_transfer)
            self._transfers.append(transfer)
            transfer.submit()
        self._event_thread = threading.Thread(
            target=self._handle_events, name="usb-events", daemon=True
        )
        self._event_thread.start()

    def _handle_events(self) -> None:
        assert self._context is not None

        while self._running:
            started = time.monotonic()
            try:
                self._context.handleEventsTimeout(tv=self.EVENT_TIMEOUT_S)
            except usb1.USBErrorInterrupted:
                pass
            except usb1.USBError as exc:
                self._set_error(exc)
                return
            self._polled_at = started

        # Let the cancelled transfers complete, so that their buffers aren't freed while in use
        deadline = time.monotonic() + self.CLOSE_TIMEOUT_S
        while any(t.isSubmitted() for t in self._transfers) and time.monotonic() < deadline:
            with contextlib.suppress(usb1.USBError):
                self._context.handleEventsTimeout(tv=self.EVENT_TIMEOUT_S)

    def _on_transfer(self, transfer: usb1.USBTransfer) -> None:
        """Collect a completed read and queue it again. Runs in the event thread."""
        status = transfer.getStatus()
        if status == usb1.TRANSFER_CANCELLED:
            return
        if status != usb1.TRANSFER_COMPLETED:
            self._set_error(UsbPortError(f"USB read failed with transfer status {status}"))
            return

        with self._rx_condition:
            length = transfer.getActualLength()
            if length > 0:
                self._rx += transfer.getBuffer()[:length]
                self._rx_condition.notify_all()
            if not self._running:
                return
            if len(self._rx) >= self.MAX_BUFFERED:
                self._parked.append(transfer)
                return
        self._submit(transfer)

    def _submit(self, transfer: usb1.USBTransfer) -> None:
        try:
            transfer.submit()
        except usb1.USBError as exc:
            self._set_error(exc)

    def _set_error(self, exc: Exception) -> None:
        with self._rx_condition:
            if self._error is None:
                self._error = exc
            self._rx_condition.notify_all()

    def _take(self, num_bytes: int) -> bytes:
        """Remove and return the first num_bytes of the buffer. Call with the lock held."""
        data = bytes(self._rx[:num_bytes])
        del self._rx[:num_bytes]
        if self._parked and len(self._rx) < self.MAX_BUFFERED and self._running:
            parked, self._parked = self._parked, []
            for transfer in parked:
                self._submit(transfer)
        return data

    def _wait(self, deadline: float) -> None:
        """Wait for more data. Call with the lock held."""
        if self._error is not None:
            raise self._error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Time out only once the event thread has collected what arrived before the
            # deadline, in a poll started after it. If the process was suspended or starved
            # past the deadline, the data may be waiting in the OS, and a poll that was already
            # running may return before collecting it.
            thread = self._event_thread
            if self._polled_at > deadline or thread is None or not thread.is_alive():
                msg = "USB read timeout"
                raise TimeoutError(msg)
            remaining = self.EVENT_TIMEOUT_S
        self._rx_condition.wait(timeout=remaining)

    def read(self, num_bytes: int, timeout: float) -> bytes:
        """Return exactly num_bytes, waiting at most timeout seconds for them to arrive."""
        deadline = time.monotonic() + timeout
        with self._rx_condition:
            while len(self._rx) < num_bytes:
                self._wait(deadline)
            return self._take(num_bytes)

    def read_until(self, terminator: bytes, timeout: float) -> bytes:
        """Return everything up to and including terminator, waiting at most timeout seconds."""
        deadline = time.monotonic() + timeout
        searched = 0
        with self._rx_condition:
            while True:
                i = self._rx.find(terminator, searched)
                if i >= 0:
                    return self._take(i + len(terminator))
                searched = max(len(self._rx) - len(terminator) + 1, 0)
                self._wait(deadline)

    def write(self, data: bytes) -> None:
        assert self._handle is not None
        sent = self._handle.bulkWrite(self._ep_out, data, timeout=self.WRITE_TIMEOUT_MS)
        if sent != len(data):
            msg = f"USB write sent {sent} of {len(data)} bytes"
            raise UsbPortError(msg)

    def send_break(self) -> None:
        assert self._handle is not None
        self._handle.controlWrite(
            usb1.TYPE_CLASS | usb1.RECIPIENT_INTERFACE,
            self.USB_CDC_CMD_SEND_BREAK,
            0xFFFF,
            0,
            b"",
            timeout=self.CONTROL_TIMEOUT_MS,
        )

    def reset_input_buffer(self, quiet_s: float) -> None:
        """Discard all received data, until nothing has arrived for quiet_s seconds"""
        with self._rx_condition:
            while True:
                self._take(len(self._rx))
                if not self._rx_condition.wait_for(lambda: len(self._rx) > 0, timeout=quiet_s):
                    break

    def close(self) -> None:
        atexit.unregister(self.close)
        self._running = False
        for transfer in self._transfers:
            if transfer.isSubmitted():
                with contextlib.suppress(usb1.USBError):
                    transfer.cancel()
        if self._event_thread is not None:
            self._event_thread.join()
            self._event_thread = None
        if self._handle is not None:
            if self._interface_number is not None:
                with contextlib.suppress(usb1.USBError):
                    self._handle.releaseInterface(self._interface_number)
            with contextlib.suppress(usb1.USBError):
                self._handle.close()
            self._handle = None
        self._transfers = []
        self._parked = []
        if self._context is not None:
            with contextlib.suppress(usb1.USBError):
                self._context.close()
            self._context = None


class USBLink(BufferedLink):
    # Discard incoming data after a break until nothing has arrived for this long
    BREAK_QUIET_S = 0.2

    def __init__(
        self, vid: int | None = None, pid: int | None = None, serial: str | None = None
    ) -> None:
        super().__init__()
        self._vid = vid
        self._pid = pid
        self._serial = serial
        self._port: AsyncUsbBulk | None = None

    def _update_timeout(self) -> None:
        # timeout is manually handled in recv/recv_until
        pass

    def connect(self) -> None:
        if not (self._vid and self._pid):
            msg = "Must have vid and pid for usb device"
            raise LinkError(msg)

        self._port = AsyncUsbBulk(vid=self._vid, pid=self._pid, serial=self._serial)
        try:
            self._port.open()
        except BaseException:
            self._port = None
            raise
        self.send_break()

    def send_break(self) -> None:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        try:
            self._port.send_break()
        except usb1.USBError as e:
            raise LinkError from e
        time.sleep(1.0)
        self._port.reset_input_buffer(self.BREAK_QUIET_S)

    def recv(self, num_bytes: int) -> bytes:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        try:
            return self._port.read(num_bytes, self._timeout)
        except TimeoutError as e:
            msg = "recv timeout"
            raise LinkError(msg) from e
        except (usb1.USBError, UsbPortError) as e:
            raise LinkError from e

    def recv_until(self, bs: bytes) -> bytes:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)

        try:
            return self._port.read_until(bs, self._timeout)
        except TimeoutError as e:
            msg = "recv timeout"
            raise LinkError(msg) from e
        except (usb1.USBError, UsbPortError) as e:
            raise LinkError from e

    def send(self, data: bytes) -> None:
        if self._port is None:
            msg = "Port is not connected"
            raise LinkError(msg)
        try:
            self._port.write(data)
        except (usb1.USBError, UsbPortError) as e:
            raise LinkError from e

    def disconnect(self) -> None:
        if self._port is not None:
            self._port.close()
            self._port = None


class LegacyUSBLink(BufferedLink):
    """The USB link before USBLink, which reads only when the client asks for data.

    Kept as a fallback, selected with the ET_LEGACY_USB environment variable.
    """

    def __init__(
        self, vid: int | None = None, pid: int | None = None, serial: str | None = None
    ) -> None:
        super().__init__()
        self._vid = vid
        self._pid = pid
        self._serial = serial
        self._port: PyUsbCdc | None = None

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

        t0 = time.monotonic()
        while len(self._buf) < num_bytes:
            if time.monotonic() - t0 > self._timeout:
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

        t0 = time.monotonic()
        while True:
            try:
                i = self._buf.index(bs)
            except ValueError:
                pass
            else:
                break

            if time.monotonic() - t0 > self._timeout:
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
