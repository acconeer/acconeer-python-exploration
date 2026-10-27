# Copyright (c) Acconeer AB, 2026
# All rights reserved

import types

import pytest

from acconeer.exptool._core.communication.links import LegacyUSBLink, USBLink, helpers
from acconeer.exptool._core.entities import ClientInfo, USBInfo


@pytest.fixture
def usb_device(monkeypatch) -> None:
    device = types.SimpleNamespace(vid=0x0483, pid=0xA561, serial="SN1")
    monkeypatch.setattr(helpers, "get_one_usb_device", lambda: device)


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
