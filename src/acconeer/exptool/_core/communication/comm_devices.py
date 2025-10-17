# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import abc
import json
import re
from typing import Any, Iterator, List, Optional

import attrs
import serial.tools
import serial.tools.list_ports
import typing_extensions as te
import usb.core
from packaging import version

from .links.usb_link import get_libusb_backend


class CommDeviceError(Exception):
    pass


_USB_IDS = [  # (vid, pid, 'model number', 'Unflashed')
    (0x0483, 0xA41D, "XC120", True),
    (0x0483, 0xA42C, "XC120", True),
    (0x0483, 0xA42D, "XC120", False),
    (0x0483, 0xA449, "XC120", False),
    (0xACC0, 0xE121, "XV12X", False),
]


@attrs.frozen(kw_only=True)
class CommDevice(abc.ABC):
    name: Optional[str] = None
    serial: Optional[str] = None
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
    for vid, pid, model_number, unflashed in _USB_IDS:
        if port_object.vid == vid and port_object.pid == pid:
            return SerialDevice(
                name=model_number,
                port=port_object.device,
                serial=port_object.serial_number,
                unflashed=unflashed,
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


def get_serial_devices() -> List[SerialDevice]:
    serial_devices = []

    port_objects = serial.tools.list_ports.comports()
    for port_object in port_objects:
        serial_devices.append(serial_device_from_port_object(port_object))

    return serial_devices


class _UsbDeviceFinder:
    device_cache: dict[str, bool] = {}

    def __init__(self) -> None:
        self._backend = get_libusb_backend()

    def iterate_devices(self) -> Iterator[tuple[int, int, Optional[str]]]:
        devices = usb.core.find(find_all=True, backend=self._backend)
        for dev in devices:
            try:
                serial_number = dev.serial_number
            except (ValueError, NotImplementedError):
                serial_number = None
            vid = dev.idVendor
            pid = dev.idProduct
            usb.util.dispose_resources(dev)
            yield (vid, pid, serial_number)

    def is_accessible(self, vid: int, pid: int) -> bool:
        vid_pid_str = f"{vid:04x}:{pid:04x}"
        if vid_pid_str not in self.device_cache:
            try:
                device = usb.core.find(idVendor=vid, idProduct=pid, backend=self._backend)
                # This will raise an USBError exception if inaccessible
                device.set_configuration()
                self.device_cache[vid_pid_str] = True
            except usb.core.USBError:
                self.device_cache[vid_pid_str] = False
            except NotImplementedError:
                # The function set_configuration is not implemented in windows libusb
                self.device_cache[vid_pid_str] = True

        return self.device_cache[vid_pid_str]


def get_usb_devices(only_accessible: bool = False) -> List[USBDevice]:
    usb_devices: List[USBDevice] = []

    usb_device_finder = _UsbDeviceFinder()
    for device_vid, device_pid, serial_number in usb_device_finder.iterate_devices():
        for vid, pid, model_name, unflashed in _USB_IDS:
            if device_vid == vid and device_pid == pid:
                device_name = model_name
                accessible = usb_device_finder.is_accessible(vid, pid)
                if only_accessible and not accessible:
                    continue

                usb_devices.append(
                    USBDevice(
                        vid=device_vid,
                        pid=device_pid,
                        serial=serial_number,
                        name=device_name,
                        accessible=accessible,
                        unflashed=unflashed,
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


def get_one_usb_device(only_accessible: bool = False) -> USBDevice:
    usb_devices = get_usb_devices(only_accessible=only_accessible)
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
    acconeer_serial_devices: List[SerialDevice] = [
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
) -> list[tuple[serial.Serial, Optional[str]]]:
    PRODUCT_REGEX = r"[X][A-Z]\d{3}"

    port_tag_tuples: list[tuple[serial.Serial, Optional[str]]] = []

    for port_object in port_infos:
        desc = port_object.product or port_object.description

        match = re.search(PRODUCT_REGEX, desc)
        if match is None:
            for vid, pid, model_number, _ in _USB_IDS:
                if port_object.vid == vid and port_object.pid == pid:
                    port_tag_tuples.append((port_object, model_number))
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
