# Copyright (c) Acconeer AB, 2026
# All rights reserved

import types

import pytest

from acconeer.exptool._core.communication import comm_devices
from acconeer.exptool._core.communication.links import LegacyUSBLink, USBLink, helpers
from acconeer.exptool._core.entities import ClientInfo, USBInfo


@pytest.fixture
def usb_device(monkeypatch) -> None:
    device = types.SimpleNamespace(vid=0x0483, pid=0xA561, serial="SN1")
    monkeypatch.setattr(helpers, "get_one_usb_device", lambda **_: device)


@pytest.mark.parametrize(
    ("env", "link_class"),
    [
        (None, USBLink),
        ("", USBLink),
        ("0", USBLink),
        ("1", LegacyUSBLink),
    ],
)
def test_et_legacy_usb_selects_the_usb_link(usb_device, monkeypatch, env, link_class):
    if env is None:
        monkeypatch.delenv("ET_LEGACY_USB", raising=False)
    else:
        monkeypatch.setenv("ET_LEGACY_USB", env)

    link = helpers.link_factory(ClientInfo(usb=USBInfo()))

    assert type(link) is link_class


class _UsbDeviceFinder:
    """An XC120, serving A121 sensors, and an XE212 in its bootloader, serving A2 ones"""

    def iterate_devices(self):
        yield (0x0483, 0xA449, "XC120")
        yield (0x0483, 0xA560, "XE212")

    def is_accessible(self, vid, pid):
        return True


@pytest.mark.parametrize(("generation", "name"), [("a121", "XC120"), ("a2", "XE212")])
def test_autodetection_picks_the_board_of_the_clients_generation(monkeypatch, generation, name):
    monkeypatch.setattr(comm_devices, "_UsbDeviceFinder", _UsbDeviceFinder)

    client_info = helpers.autodetermine_client_info(ClientInfo(), generation)

    assert client_info.usb is not None
    assert client_info.usb.serial_number == name


def test_autodetection_without_a_generation_sees_every_board(monkeypatch):
    monkeypatch.setattr(comm_devices, "_UsbDeviceFinder", _UsbDeviceFinder)

    with pytest.raises(comm_devices.CommDeviceError, match="multiple devices"):
        comm_devices.get_one_usb_device(only_accessible=True)
