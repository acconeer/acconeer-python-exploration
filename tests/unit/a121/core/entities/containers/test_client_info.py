import pytest

from acconeer.exptool.a121 import ClientInfo
from acconeer.exptool.utils import USBDevice  # type: ignore[import]


@pytest.fixture
def client_info():
    return ClientInfo(
        ip_address="addr",
        serial_port="port",
        usb_device=USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name"),
        override_baudrate=0,
    )


@pytest.fixture
def client_info_dict():
    return {
        "ip_address": "addr",
        "serial_port": "port",
        "usb_device": {"vid": 0x4CC0, "pid": 0xAEE3, "serial": None, "name": "name"},
        "override_baudrate": 0,
    }


def test_init(client_info):
    assert client_info.ip_address == "addr"
    assert client_info.serial_port == "port"
    assert client_info.usb_device == USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name")
    assert client_info.override_baudrate == 0


def test_eq(client_info):
    assert client_info == ClientInfo(
        ip_address="addr",
        serial_port="port",
        usb_device=USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name"),
        override_baudrate=0,
    )
    assert client_info != ClientInfo(
        ip_address="ddr",
        serial_port="port",
        usb_device=USBDevice(vid=0x4CC0, pid=0xAEE3, serial=None, name="name"),
        override_baudrate=0,
    )


def test_to_dict(client_info, client_info_dict):
    assert client_info.to_dict() == client_info_dict


def test_from_dict(client_info, client_info_dict):
    assert ClientInfo.from_dict(client_info_dict) == client_info


def test_to_from_dict_equality(client_info):
    assert client_info == ClientInfo.from_dict(client_info.to_dict())


def test_from_dict_extra_kwarg(client_info_dict):
    client_info_dict["extra"] = "kwarg"
    with pytest.raises(TypeError):
        ClientInfo.from_dict(client_info_dict)


def test_to_from_json_equality(client_info):
    assert client_info == ClientInfo.from_json(client_info.to_json())
