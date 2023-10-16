# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

from typing import Any, Tuple

import pytest

from acconeer.exptool import USBDevice
from acconeer.exptool._core import ClientInfo, MockInfo, SerialInfo, SocketInfo, USBInfo
from acconeer.exptool._core.communication.comm_devices import SerialDevice


CLIENT_INFO_PARAMETRIZE = [
    (
        dict(ip_address="addr", tcp_port=None),
        {
            "serial": None,
            "usb": None,
            "socket": {"ip_address": "addr", "tcp_port": None},
            "mock": None,
        },
    ),
    (
        dict(serial_port="port", override_baudrate=0),
        {
            "serial": {"port": "port", "override_baudrate": 0, "serial_number": None},
            "usb": None,
            "socket": None,
            "mock": None,
        },
    ),
    (
        dict(usb_device=True),
        {
            "serial": None,
            "socket": None,
            "mock": None,
            "usb": {"vid": None, "pid": None, "serial_number": None},
        },
    ),
    (
        dict(usb_device="1234"),
        {
            "serial": None,
            "usb": {"vid": None, "pid": None, "serial_number": "1234"},
            "socket": None,
            "mock": None,
        },
    ),
    (
        dict(mock=True),
        {
            "serial": None,
            "usb": None,
            "socket": None,
            "mock": {},
        },
    ),
]


@pytest.fixture(params=CLIENT_INFO_PARAMETRIZE)
def client_info_fixture(request: pytest.FixtureRequest) -> Tuple[ClientInfo, dict[str, Any]]:
    from_open_args = request.param[0]
    client_info_dict = request.param[1]
    return (ClientInfo._from_open(**from_open_args), client_info_dict)


def test_to_dict(client_info_fixture: Tuple[ClientInfo, dict[str, Any]]) -> None:
    client_info = client_info_fixture[0]
    client_info_dict = client_info_fixture[1]
    assert client_info.to_dict() == client_info_dict


def test_from_dict(client_info_fixture: Tuple[ClientInfo, dict[str, Any]]) -> None:
    client_info = client_info_fixture[0]
    client_info_dict = client_info_fixture[1]
    assert ClientInfo.from_dict(client_info_dict) == client_info


def test_to_from_dict_equality(client_info_fixture: Tuple[ClientInfo, dict[str, Any]]) -> None:
    client_info = client_info_fixture[0]
    assert client_info == ClientInfo.from_dict(client_info.to_dict())


def test_from_dict_extra_kwarg(client_info_fixture: Tuple[ClientInfo, dict[str, Any]]) -> None:
    client_info_dict = client_info_fixture[1]
    client_info_dict["extra"] = "kwarg"
    with pytest.raises(TypeError):
        ClientInfo.from_dict(client_info_dict)


def test_to_from_json_equality(client_info_fixture: Tuple[ClientInfo, dict[str, Any]]) -> None:
    client_info = client_info_fixture[0]
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


@pytest.mark.parametrize(
    "pre_v6_json,expected",
    [
        pytest.param(
            """{
                "ip_address": null,
                "serial_port": null,
                "mock": null,
                "override_baudrate": null,
                "usb_device": {
                    "name": "XC120",
                    "serial": "000000000000",
                    "unflashed": false,
                    "recognized": true,
                    "vid": 1155,
                    "pid": 42029,
                    "accessible": true
                }
            }""",
            ClientInfo(usb=USBInfo(vid=1155, pid=42029, serial_number="000000000000")),
            id="USB ClientInfo",
        ),
        pytest.param(
            """{
                "ip_address": "localhost",
                "tcp_port": 1337,
                "serial_port": null,
                "mock": null,
                "override_baudrate": null,
                "usb_device": null
            }""",
            ClientInfo(socket=SocketInfo(ip_address="localhost", tcp_port=1337)),
            id="Socket ClientInfo",
        ),
        pytest.param(
            """{
                "ip_address": "localhost",
                "serial_port": null,
                "mock": null,
                "override_baudrate": null,
                "usb_device": null
            }""",
            ClientInfo(socket=SocketInfo(ip_address="localhost", tcp_port=None)),
            id="Socket ClientInfo (missing tcp_port entry)",
        ),
        pytest.param(
            """{
                "ip_address": null,
                "serial_port": "/dev/ttyACM0",
                "mock": null,
                "override_baudrate": 10,
                "usb_device": null
            }""",
            ClientInfo(serial=SerialInfo(port="/dev/ttyACM0", override_baudrate=10)),
            id="Serial ClientInfo",
        ),
        pytest.param(
            """{
                "ip_address": null,
                "serial_port": null,
                "mock": true,
                "override_baudrate": null,
                "usb_device": null
            }""",
            ClientInfo(mock=MockInfo()),
            id="Mock ClientInfo",
        ),
        pytest.param(
            """{
                "ip_address": null,
                "serial_port": null,
                "override_baudrate": null,
                "usb_device": null
            }""",
            ClientInfo(),
            id="Missing mock key",
        ),
    ],
)
def test_can_migrate_pre_v6_json(pre_v6_json: str, expected: ClientInfo) -> None:
    assert ClientInfo.from_json(pre_v6_json) == expected
