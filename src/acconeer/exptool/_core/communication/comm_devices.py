# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import abc
import json
import re
from typing import Any, Iterator, Literal

import attrs
import serial.tools
import serial.tools.list_ports
import typing_extensions as te
import usb.core
from packaging import version
from serial.tools.list_ports_common import ListPortInfo

from .links.usb_link import get_libusb_backend, get_libusb_bulk_interface


class CommDeviceError(Exception):
    pass


SensorGeneration = Literal["a121", "a2"]


@attrs.frozen(kw_only=True)
class _UsbId:
    vid: int
    pid: int
    model_number: str
    unflashed: bool
    generation: SensorGeneration  # Of the sensors the board serves


_USB_IDS: list[_UsbId] = [
    _UsbId(vid=0x0483, pid=0xA41D, model_number="XC120", unflashed=True, generation="a121"),
    _UsbId(vid=0x0483, pid=0xA42C, model_number="XC120", unflashed=True, generation="a121"),
    _UsbId(vid=0x0483, pid=0xA42D, model_number="XC120", unflashed=False, generation="a121"),
    _UsbId(vid=0x0483, pid=0xA449, model_number="XC120", unflashed=False, generation="a121"),
    _UsbId(vid=0x0483, pid=0xA560, model_number="XE212", unflashed=True, generation="a2"),
    _UsbId(vid=0x0483, pid=0xA561, model_number="XE212", unflashed=False, generation="a2"),
    _UsbId(vid=0x0483, pid=0xA562, model_number="XE212", unflashed=True, generation="a2"),
    _UsbId(vid=0xACC0, pid=0xE121, model_number="XV12X", unflashed=False, generation="a121"),
    _UsbId(vid=0xACC0, pid=0xD211, model_number="XV21X", unflashed=False, generation="a2"),
    _UsbId(vid=0xACC0, pid=0xB211, model_number="XC211", unflashed=True, generation="a2"),
    _UsbId(vid=0xACC0, pid=0xE211, model_number="XC211", unflashed=False, generation="a2"),
]


@attrs.frozen(kw_only=True)
class CommDevice(abc.ABC):
    name: str | None = None
    serial: str | None = None
    unflashed: bool = False
    recognized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> te.Self:
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> te.Self:
        return cls.from_dict(json.loads(json_str))

    @abc.abstractmethod
    def display_name(self) -> str:
        pass


@attrs.frozen(kw_only=True)
class SerialDevice(CommDevice):
    port: str

    def display_name(self) -> str:
        if self.name is not None:
            dev_name = f"{self.name} {self.port}"
        else:
            dev_name = f"{self.port}"

        if self.unflashed:
            display_name = f"Unflashed {dev_name}"
        elif self.serial is not None:
            display_name = f"{dev_name} ({self.serial})"
        else:
            display_name = dev_name
        return display_name

    def __str__(self) -> str:
        name_str = "" if self.name is None else f"{self.name}: "
        serial_str = "?" if self.serial is None else self.serial
        return f"{name_str}port={self.port} serial={serial_str}"


@attrs.frozen(kw_only=True)
class USBDevice(CommDevice):
    vid: int
    pid: int
    accessible: bool = True

    def display_name(self) -> str:
        if not self.accessible:
            display_name = f"{self.name} (inaccessible)"
        elif self.unflashed:
            display_name = f"Unflashed {self.name}"
        elif self.serial is not None:
            display_name = f"{self.name} ({self.serial})"
        else:
            display_name = f"{self.name}"
        return display_name

    def __str__(self) -> str:
        serial_str = "?" if self.serial is None else self.serial
        return (
            f"{self.name}: USB_VID=0x{self.vid:04x}, USB_PID=0x{self.pid:04x} serial={serial_str}"
        )


def serial_device_from_port_object(port_object: serial.Serial) -> SerialDevice:
    # Return USB serial port if existing in _USB_IDS
    for usb_id in _USB_IDS:
        if port_object.vid == usb_id.vid and port_object.pid == usb_id.pid:
            return SerialDevice(
                name=usb_id.model_number,
                port=port_object.device,
                serial=port_object.serial_number,
                unflashed=usb_id.unflashed,
                recognized=True,
            )

    # Find serial portTryReturn USB serial port if existing in _USB_IDS
    device_port = port_object.device
    device_name = None
    device_serial_number = port_object.serial_number
    device_unflashed = False
    device_recognized = False

    PRODUCT_REGEX = r"[X][A-Z]\d{3}"
    desc = port_object.product or port_object.description
    match = re.search(PRODUCT_REGEX, desc)

    if match is None:
        pass
    elif match.group().lower() in ["xe123", "xe124", "xe125", "xe132"]:
        if version.parse(serial.__version__) >= version.parse("3.5"):
            # Special handling of cp2105 modules with with pyserial >= 3.5
            interface = port_object.interface

            if interface and "enhanced" in interface.lower():
                # Add the "enhanced" interface
                device_name = match.group().upper()
                device_recognized = True

        else:  # pyserial <= 3.4
            # Add "?" to both to indicate that it could be either.
            device_name = f"{match.group().upper()} (?)"
    else:
        device_recognized = True
        device_name = f"{match.group().upper()}"

    if desc is not None and "Bootloader" in desc:
        device_unflashed = True

    return SerialDevice(
        name=device_name,
        port=device_port,
        serial=device_serial_number,
        unflashed=device_unflashed,
        recognized=device_recognized,
    )


def _serial_port_originates_from_usb_device(port_object: ListPortInfo) -> bool:
    # Test if this port_object is connected to an exploration server device (unflashed = False)
    for usb_id in _USB_IDS:
        if (
            port_object.vid == usb_id.vid
            and port_object.pid == usb_id.pid
            and not usb_id.unflashed
        ):
            return True
    return False


def get_serial_devices() -> list[SerialDevice]:
    NATIVE_SERIAL_PORT_FILTER = re.compile(r"^/dev/ttyS\d{1,2}$")
    serial_devices = []

    port_objects = serial.tools.list_ports.comports()
    for port_object in port_objects:
        if bool(NATIVE_SERIAL_PORT_FILTER.match(port_object.device)):
            continue
        if _serial_port_originates_from_usb_device(port_object):
            # Do not show serial ports from an exploration server USB device
            continue
        serial_devices.append(serial_device_from_port_object(port_object))

    return serial_devices


class _UsbDeviceFinder:
    device_cache: dict[str, bool] = {}

    def __init__(self) -> None:
        self._backend = get_libusb_backend()

    def iterate_devices(self) -> Iterator[tuple[int, int, str | None]]:
        devices = usb.core.find(find_all=True, backend=self._backend)
        for dev in devices:
            try:
                serial_number = dev.serial_number
            except (ValueError, NotImplementedError, usb.core.USBError):
                serial_number = None

            try:
                vid = dev.idVendor
                pid = dev.idProduct

                if get_libusb_bulk_interface(dev) is None:
                    continue
            except usb.core.USBError:
                continue
            finally:
                usb.util.dispose_resources(dev)

            yield (vid, pid, serial_number)

    def is_accessible(self, vid: int, pid: int) -> bool:
        vid_pid_str = f"{vid:04x}:{pid:04x}"
        if vid_pid_str not in self.device_cache:
            try:
                device = usb.core.find(idVendor=vid, idProduct=pid, backend=self._backend)
                interface = get_libusb_bulk_interface(device)
                if interface is not None:
                    # This will raise an USBError exception if inaccessible
                    usb.util.claim_interface(device, interface.bInterfaceNumber)
                    usb.util.release_interface(device, interface.bInterfaceNumber)
                    self.device_cache[vid_pid_str] = True
                else:
                    self.device_cache[vid_pid_str] = False
            except usb.core.USBError:
                self.device_cache[vid_pid_str] = False
            except NotImplementedError:
                # The function set_configuration is not implemented in windows libusb
                self.device_cache[vid_pid_str] = True

        return self.device_cache[vid_pid_str]


def get_usb_devices(
    only_accessible: bool = False, generation: SensorGeneration | None = None
) -> list[USBDevice]:
    """Lists the recognized USB devices, only those serving sensors of generation if given"""
    usb_devices: list[USBDevice] = []

    usb_device_finder = _UsbDeviceFinder()
    for device_vid, device_pid, serial_number in usb_device_finder.iterate_devices():
        for usb_id in _USB_IDS:
            if generation is not None and usb_id.generation != generation:
                continue
            if device_vid == usb_id.vid and device_pid == usb_id.pid:
                accessible = usb_device_finder.is_accessible(usb_id.vid, usb_id.pid)
                if only_accessible and not accessible:
                    continue

                usb_devices.append(
                    USBDevice(
                        vid=device_vid,
                        pid=device_pid,
                        serial=serial_number,
                        name=usb_id.model_number,
                        accessible=accessible,
                        unflashed=usb_id.unflashed,
                        recognized=True,
                    )
                )

    return usb_devices


def get_usb_device_by_serial(serial: str, only_accessible: bool = False) -> USBDevice:
    usb_devices = get_usb_devices(only_accessible=only_accessible)
    if serial is not None:
        for device in usb_devices:
            if serial == device.serial:
                return device
    msg = f"Could not find usb device with serial number '{serial}'"
    raise ValueError(msg)


def get_one_usb_device(
    only_accessible: bool = False, generation: SensorGeneration | None = None
) -> USBDevice:
    usb_devices = get_usb_devices(only_accessible=only_accessible, generation=generation)
    if not usb_devices:
        msg = "No USB devices detected. Cannot auto detect."
        raise CommDeviceError(msg)
    elif len(usb_devices) > 1:
        devices_string = "".join([f" - {dev}\n" for dev in usb_devices])
        raise CommDeviceError(
            "There are multiple devices detected. Specify one:\n" + devices_string
        )
    else:
        return usb_devices[0]


def get_one_serial_device() -> SerialDevice:
    acconeer_serial_devices: list[SerialDevice] = [
        device for device in get_serial_devices() if device.name is not None
    ]

    if not acconeer_serial_devices:
        msg = "No serial devices detected. Cannot auto detect."
        raise CommDeviceError(msg)
    elif len(acconeer_serial_devices) > 1:
        devices_string = "".join([f" - {dev}\n" for dev in acconeer_serial_devices])
        raise CommDeviceError(
            "There are multiple devices detected. Specify one:\n" + devices_string
        )
    else:
        return acconeer_serial_devices[0]


def tag_serial_ports_objects(
    port_infos: list[serial.Serial],
) -> list[tuple[serial.Serial, str | None]]:
    PRODUCT_REGEX = r"[X][A-Z]\d{3}"

    port_tag_tuples: list[tuple[serial.Serial, str | None]] = []

    for port_object in port_infos:
        desc = port_object.product or port_object.description

        match = re.search(PRODUCT_REGEX, desc)
        if match is None:
            for usb_id in _USB_IDS:
                if port_object.vid == usb_id.vid and port_object.pid == usb_id.pid:
                    port_tag_tuples.append((port_object, usb_id.model_number))
                    break
            else:
                port_tag_tuples.append((port_object, None))
        elif match.group().lower() in ["xe123", "xe124", "xe125", "xe132"]:
            if version.parse(serial.__version__) >= version.parse("3.5"):
                # Special handling of cp2105 modules with with pyserial >= 3.5
                interface = port_object.interface

                if interface and "enhanced" in interface.lower():
                    # Add the "enhanced" interface
                    port_tag_tuples.append((port_object, f"{match.group().upper()}"))
                else:
                    # Add the "standard" interface but don't tag it
                    port_tag_tuples.append((port_object, None))

            else:  # pyserial <= 3.4
                # Add "?" to both to indicate that it could be either.
                port_tag_tuples.append((port_object, f"{match.group().upper()} (?)"))
        elif "Bootloader" in desc:
            port_tag_tuples.append((port_object, f"Unflashed {match.group()}"))
        else:
            port_tag_tuples.append((port_object, f"{match.group()}"))

    return port_tag_tuples
