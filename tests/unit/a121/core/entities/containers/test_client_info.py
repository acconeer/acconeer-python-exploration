# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

import pytest

from acconeer.exptool.a121 import ClientInfo
from acconeer.exptool.utils import SerialDevice, USBDevice  # type: ignore[import]


@pytest.fixture
def client_info() -> ClientInfo:
    return ClientInfo(
        ip_address="addr",
        tcp_port=None,
        serial_port="port",
        usb_device=USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name", recognized=True),
        override_baudrate=0,
        mock=True,
    )


@pytest.fixture
def client_info_dict() -> dict:
    return {
        "ip_address": "addr",
        "tcp_port": None,
        "serial_port": "port",
        "usb_device": {
            "vid": 0x4CC0,
            "pid": 0xAEE3,
            "serial": None,
            "name": "name",
            "accessible": True,
            "unflashed": False,
            "recognized": True,
        },
        "mock": True,
        "override_baudrate": 0,
    }


def test_init(client_info: ClientInfo) -> None:
    assert client_info.ip_address == "addr"
    assert client_info.serial_port == "port"
    assert client_info.usb_device == USBDevice(
        vid=0x4CC0, pid=0xAEE3, serial=None, name="name", recognized=True
    )
    assert client_info.override_baudrate == 0


def test_eq(client_info: ClientInfo) -> None:
    assert client_info == ClientInfo(
        ip_address="addr",
        serial_port="port",
        usb_device=USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name", recognized=True),
        override_baudrate=0,
        mock=True,
    )
    assert client_info != ClientInfo(
        ip_address="ddr",
        serial_port="port",
        usb_device=USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name", recognized=True),
        override_baudrate=0,
        mock=True,
    )


def test_to_dict(client_info: ClientInfo, client_info_dict: dict) -> None:
    assert client_info.to_dict() == client_info_dict


def test_from_dict(client_info: ClientInfo, client_info_dict: dict) -> None:
    assert ClientInfo.from_dict(client_info_dict) == client_info


def test_to_from_dict_equality(client_info: ClientInfo) -> None:
    assert client_info == ClientInfo.from_dict(client_info.to_dict())


def test_from_dict_extra_kwarg(client_info_dict: dict) -> None:
    client_info_dict["extra"] = "kwarg"
    with pytest.raises(TypeError):
        ClientInfo.from_dict(client_info_dict)


def test_to_from_json_equality(client_info: ClientInfo) -> None:
    assert client_info == ClientInfo.from_json(client_info.to_json())


def test_usb_device_display_name() -> None:
    usb_name = "DEV_NAME"
    usb_serial = "123456"

    usb_device = USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name=usb_name, recognized=True)
    assert usb_device.display_name() == usb_name

    usb_device = USBDevice(
        vid=0x4CC0, pid=0xAEE3, serial=usb_serial, name=usb_name, recognized=True
    )
    assert usb_device.display_name() == f"{usb_name} ({usb_serial})"

    usb_device = USBDevice(
        vid=0x4CC0, pid=0xAEE3, serial=usb_serial, name=usb_name, unflashed=True, recognized=True
    )
    assert usb_device.display_name() == f"Unflashed {usb_name}"

    usb_device = USBDevice(
        vid=0x4CC0, pid=0xAEE3, serial=usb_serial, name=usb_name, accessible=False, recognized=True
    )
    assert usb_device.display_name() == f"{usb_name} (inaccessible)"

    usb_device = USBDevice(
        vid=0x4CC0,
        pid=0xAEE3,
        serial=usb_serial,
        name=usb_name,
        unflashed=True,
        accessible=False,
        recognized=True,
    )
    assert usb_device.display_name() == f"{usb_name} (inaccessible)"


def test_serial_device_display_name() -> None:
    device_name = "DEV_NAME"
    port_name = "/dev/ttyACM0"
    port_serial_number = "abcdef"

    serial_device = SerialDevice(port=port_name, recognized=True)
    assert serial_device.display_name() == f"{port_name}"

    serial_device = SerialDevice(port=port_name, serial=port_serial_number, recognized=True)
    assert serial_device.display_name() == f"{port_name} ({port_serial_number})"

    serial_device = SerialDevice(port=port_name, serial=port_serial_number, recognized=True)
    assert serial_device.display_name() == f"{port_name} ({port_serial_number})"

    serial_device = SerialDevice(
        name=device_name, port=port_name, serial=port_serial_number, recognized=True
    )
    assert serial_device.display_name() == f"{device_name} {port_name} ({port_serial_number})"

    serial_device = SerialDevice(name=device_name, port=port_name, recognized=True)
    assert serial_device.display_name() == f"{device_name} {port_name}"

    serial_device = SerialDevice(
        name=device_name,
        port=port_name,
        serial=port_serial_number,
        recognized=True,
        unflashed=True,
    )
    assert serial_device.display_name() == f"Unflashed {device_name} {port_name}"
