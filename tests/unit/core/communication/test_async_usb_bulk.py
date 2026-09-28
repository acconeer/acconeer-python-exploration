# Copyright (c) Acconeer AB, 2026
# All rights reserved

import collections
import threading
import time

import pytest
import usb1

from acconeer.exptool._core.communication.links import usb_link
from acconeer.exptool._core.communication.links.buffered_link import LinkError
from acconeer.exptool._core.communication.links.usb_link import AsyncUsbBulk, USBLink, UsbPortError


class FakeTransfer:
    """Stands in for a usb1.USBTransfer that has just completed"""

    def __init__(self) -> None:
        self.status = usb1.TRANSFER_COMPLETED
        self.data = b""
        self.submits = 0

    def complete(self, data: bytes, status: int = usb1.TRANSFER_COMPLETED) -> "FakeTransfer":
        self.data = data
        self.status = status
        return self

    def getStatus(self) -> int:
        return self.status

    def getActualLength(self) -> int:
        return len(self.data)

    def getBuffer(self) -> bytearray:
        return bytearray(self.data) + bytearray(16)

    def submit(self) -> None:
        self.submits += 1

    def isSubmitted(self) -> bool:
        return False


@pytest.fixture
def port() -> AsyncUsbBulk:
    port = AsyncUsbBulk(vid=1, pid=2)
    port._running = True
    return port


def test_completed_reads_are_resubmitted_and_read_in_order(port):
    transfer = FakeTransfer()
    port._on_transfer(transfer.complete(b"hello "))
    port._on_transfer(transfer.complete(b"world"))

    assert transfer.submits == 2
    assert port.read(3, timeout=0) == b"hel"
    assert port.read(8, timeout=0) == b"lo world"


def test_read_until_finds_a_terminator_split_across_reads(port):
    transfer = FakeTransfer()
    port._on_transfer(transfer.complete(b'{"status":"ok"}\r'))
    port._on_transfer(transfer.complete(b"\npayload"))

    assert port.read_until(b"\r\n", timeout=0) == b'{"status":"ok"}\r\n'
    assert port.read(7, timeout=0) == b"payload"


def test_read_times_out_without_enough_data(port):
    port._on_transfer(FakeTransfer().complete(b"ab"))

    with pytest.raises(TimeoutError):
        port.read(3, timeout=0.01)
    with pytest.raises(TimeoutError):
        port.read_until(b"\n", timeout=0.01)


def test_failed_read_is_raised_once_the_buffer_is_used_up(port):
    transfer = FakeTransfer()
    port._on_transfer(transfer.complete(b"ab"))
    port._on_transfer(transfer.complete(b"", status=usb1.TRANSFER_NO_DEVICE))

    assert transfer.submits == 1
    assert port.read(2, timeout=0) == b"ab"
    with pytest.raises(UsbPortError):
        port.read(1, timeout=1)


def test_cancelled_and_stopped_reads_are_not_resubmitted(port):
    transfer = FakeTransfer()
    port._on_transfer(transfer.complete(b"", status=usb1.TRANSFER_CANCELLED))
    port._running = False
    port._on_transfer(transfer.complete(b"late"))

    assert transfer.submits == 0
    assert port.read(4, timeout=0) == b"late"


def test_reads_stop_when_the_buffer_is_full_and_resume_when_drained(port, monkeypatch):
    monkeypatch.setattr(AsyncUsbBulk, "MAX_BUFFERED", 4)
    transfer = FakeTransfer()
    port._on_transfer(transfer.complete(b"abcd"))

    assert transfer.submits == 0
    assert port.read(1, timeout=0) == b"a"
    assert transfer.submits == 1


def test_reset_input_buffer_discards_everything(port):
    port._on_transfer(FakeTransfer().complete(b"stale data"))
    port.reset_input_buffer(quiet_s=0.01)

    with pytest.raises(TimeoutError):
        port.read(1, timeout=0.01)


# Fakes of the usb1 objects the link uses, so that the whole open / stream / close cycle runs
# in its event thread without libusb or a USB device.

VID, PID = 0x0483, 0xA561
EP_IN, EP_OUT = 0x81, 0x01


class FakeEndpoint:
    def __init__(self, address: int) -> None:
        self._address = address

    def getAddress(self) -> int:
        return self._address

    def getAttributes(self) -> int:
        return usb1.TRANSFER_TYPE_BULK


class FakeSetting:
    def __init__(self, number: int, interface_class: int, endpoints: list[FakeEndpoint]) -> None:
        self._number = number
        self._class = interface_class
        self._endpoints = endpoints

    def getNumber(self) -> int:
        return self._number

    def getClass(self) -> int:
        return self._class

    def getNumEndpoints(self) -> int:
        return len(self._endpoints)

    def __iter__(self):
        return iter(self._endpoints)


class FakeBus:
    """A device's data and state, shared between the test and the event thread"""

    def __init__(self, serial: str = "SN1") -> None:
        self.serial = serial
        self.lock = threading.Lock()
        self.incoming: collections.deque[bytes] = collections.deque()
        self.fail_status: int | None = None
        self.written = bytearray()
        self.breaks = 0
        self.claimed = False
        self.transfers: list[FakeAsyncTransfer] = []
        self.handle_closed = False
        self.context_closed = False


class FakeAsyncTransfer:
    def __init__(self, bus: FakeBus) -> None:
        self._bus = bus
        self._submitted = False
        self._cancel = False
        self._status = 0
        self._data = b""
        self._callback = None

    def setBulk(self, endpoint, size, callback=None):
        assert endpoint == EP_IN
        self._callback = callback

    def submit(self) -> None:
        assert not self._submitted
        self._submitted = True
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def isSubmitted(self) -> bool:
        return self._submitted

    def getStatus(self) -> int:
        return self._status

    def getActualLength(self) -> int:
        return len(self._data)

    def getBuffer(self) -> bytearray:
        return bytearray(self._data)

    def complete(self, status: int, data: bytes = b"") -> None:
        self._submitted = False
        self._status = status
        self._data = data
        self._callback(self)


class FakeHandle:
    def __init__(self, bus: FakeBus, device: "FakeDevice") -> None:
        self._bus = bus
        self._device = device

    def getDevice(self) -> "FakeDevice":
        return self._device

    def getSerialNumber(self) -> str:
        return self._bus.serial

    def resetDevice(self) -> None:
        pass

    def claimInterface(self, number: int) -> None:
        assert number == 1
        self._bus.claimed = True

    def releaseInterface(self, number: int) -> None:
        self._bus.claimed = False

    def getTransfer(self) -> FakeAsyncTransfer:
        transfer = FakeAsyncTransfer(self._bus)
        self._bus.transfers.append(transfer)
        return transfer

    def bulkWrite(self, endpoint: int, data: bytes, timeout: int = 0) -> int:
        assert endpoint == EP_OUT
        self._bus.written += data
        return len(data)

    def controlWrite(self, request_type, request, value, index, data, timeout=0) -> int:
        assert request == AsyncUsbBulk.USB_CDC_CMD_SEND_BREAK
        self._bus.breaks += 1
        return 0

    def close(self) -> None:
        assert not any(t.isSubmitted() for t in self._bus.transfers), (
            "closed with transfers in flight"
        )
        self._bus.handle_closed = True


class FakeDevice:
    def __init__(self, bus: FakeBus) -> None:
        self._bus = bus

    def getVendorID(self) -> int:
        return VID

    def getProductID(self) -> int:
        return PID

    def open(self) -> FakeHandle:
        return FakeHandle(self._bus, self)

    def iterConfigurations(self):
        cdc = FakeSetting(0, 0x02, [FakeEndpoint(0x82)])
        vendor = FakeSetting(1, 0xFF, [FakeEndpoint(EP_IN), FakeEndpoint(EP_OUT)])
        return iter([[[cdc], [vendor]]])


class FakeContext:
    bus = FakeBus()

    def open(self) -> None:
        pass

    def getDeviceIterator(self, skip_on_error=False):
        return iter([FakeDevice(self.bus)])

    def handleEventsTimeout(self, tv=0) -> None:
        """Complete one submitted transfer: cancelled, failed, or with the next chunk of data"""
        bus = self.bus
        with bus.lock:
            submitted = [t for t in bus.transfers if t.isSubmitted()]
            cancelled = [t for t in submitted if t._cancel]
            if cancelled:
                event = (cancelled[0], usb1.TRANSFER_CANCELLED, b"")
            elif submitted and bus.fail_status is not None:
                event = (submitted[0], bus.fail_status, b"")
            elif submitted and bus.incoming:
                event = (submitted[0], usb1.TRANSFER_COMPLETED, bus.incoming.popleft())
            else:
                event = None
        if event is None:
            threading.Event().wait(0.001)
        else:
            event[0].complete(event[1], event[2])

    def close(self) -> None:
        self.bus.context_closed = True


@pytest.fixture
def bus(monkeypatch) -> FakeBus:
    bus = FakeBus()
    monkeypatch.setattr(FakeContext, "bus", bus)
    monkeypatch.setattr(usb1, "USBContext", FakeContext)
    monkeypatch.setattr(usb_link, "load_usb1_library", lambda: None)
    return bus


def event_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "usb-events"]


def test_streams_writes_and_closes_cleanly(bus):
    port = AsyncUsbBulk(vid=VID, pid=PID)
    port.open()
    assert bus.claimed
    assert sum(t.isSubmitted() for t in bus.transfers) == AsyncUsbBulk.TRANSFER_COUNT

    bus.incoming.extend([b'{"status":"ok"}\n', b"payload"])
    assert port.read_until(b"\n", timeout=2) == b'{"status":"ok"}\n'
    assert port.read(7, timeout=2) == b"payload"
    port.write(b'{"cmd":"get_system_info"}\n')
    port.send_break()
    assert bytes(bus.written) == b'{"cmd":"get_system_info"}\n'
    assert bus.breaks == 1

    port.close()
    assert not event_threads()
    assert not any(t.isSubmitted() for t in bus.transfers)
    assert not bus.claimed
    assert bus.handle_closed
    assert bus.context_closed


def test_a_device_with_another_serial_is_not_opened(bus):
    port = AsyncUsbBulk(vid=VID, pid=PID, serial="SN2")
    with pytest.raises(UsbPortError):
        port.open()
    assert bus.context_closed
    assert not event_threads()


def test_a_failed_transfer_reaches_the_reader_and_close_does_not_hang(bus):
    port = AsyncUsbBulk(vid=VID, pid=PID)
    port.open()
    bus.incoming.append(b"last")
    assert port.read(4, timeout=2) == b"last"
    bus.fail_status = usb1.TRANSFER_NO_DEVICE

    with pytest.raises(UsbPortError):
        port.read(1, timeout=2)
    port.close()
    assert not event_threads()
    assert bus.handle_closed


def test_a_read_past_its_deadline_waits_for_the_event_thread(bus):
    port = AsyncUsbBulk(vid=VID, pid=PID)
    port.open()
    # Hold up the event thread past the read's deadline, as when the whole process is suspended,
    # while the data has already arrived
    bus.lock.acquire()
    bus.incoming.append(b"late")
    threading.Timer(0.3, bus.lock.release).start()

    try:
        assert port.read(4, timeout=0.05) == b"late"
    finally:
        port.close()


def test_a_poll_already_running_at_the_deadline_does_not_end_the_read(bus, monkeypatch):
    port = AsyncUsbBulk(vid=VID, pid=PID)
    port.open()
    stall, stalled, slow_next = threading.Event(), threading.Event(), threading.Event()
    handle_events = FakeContext.handleEventsTimeout

    def suspended_poll(self, tv=0):
        if stall.is_set():
            # As after a suspend: the data arrives while a poll that began before the read's
            # deadline is running, and that poll returns after the deadline without collecting
            # it. The next poll is slow to start, so the reader gets to check in between.
            stall.clear()
            stalled.set()
            bus.incoming.append(b"late")
            time.sleep(0.3)
            slow_next.set()
            return
        if slow_next.is_set():
            slow_next.clear()
            time.sleep(0.2)
        handle_events(self, tv)

    monkeypatch.setattr(FakeContext, "handleEventsTimeout", suspended_poll)
    stall.set()
    assert stalled.wait(timeout=2)

    try:
        assert port.read(4, timeout=0.05) == b"late"
    finally:
        port.close()


def test_a_port_left_open_is_closed_at_exit(bus, monkeypatch):
    exit_handlers = []

    class FakeAtexit:
        register = exit_handlers.append

        @staticmethod
        def unregister(func) -> None:
            while func in exit_handlers:
                exit_handlers.remove(func)

    monkeypatch.setattr(usb_link, "atexit", FakeAtexit)
    port = AsyncUsbBulk(vid=VID, pid=PID)
    port.open()
    assert exit_handlers == [port.close]

    exit_handlers[0]()
    assert not event_threads()
    assert bus.handle_closed
    assert exit_handlers == []


def test_link_recv_and_errors(bus, monkeypatch):
    monkeypatch.setattr(usb_link.time, "sleep", lambda _: None)
    link = USBLink(vid=VID, pid=PID)
    link.timeout = 0.2
    link.connect()
    assert bus.breaks == 1

    bus.incoming.extend([b'{"status":"start"}\n', b"\x01\x02"])
    assert link.recv_until(b"\n") == b'{"status":"start"}\n'
    assert link.recv(2) == b"\x01\x02"
    with pytest.raises(LinkError, match="recv timeout"):
        link.recv(1)

    bus.fail_status = usb1.TRANSFER_NO_DEVICE
    with pytest.raises(LinkError):
        link.recv(1)
    link.disconnect()
    assert not event_threads()
