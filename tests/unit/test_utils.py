import sys

import pytest
import serial
from serial.tools.list_ports_common import ListPortInfo

from acconeer.exptool import utils


pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Windows unsupported")


@pytest.fixture
def mock_comports():
    mock_port_attrs = [
        {
            "device": "/dev/ttyS4",
        },
        {  # XB112 ~ as given from serial.tools.list_ports.comports
            "device": "/dev/ttyUSB0",
            "description": "XB112",
            "manufacturer": "Acconeer AB",
            "product": "XB112",
            "interface": None,
        },
        {  # XE132 ~ as given ...
            "device": "/dev/ttyUSB1",
            "description": "Acconeer XE132 - Enhanced Com Port",
            "manufacturer": "Silicon Labs",
            "product": "Acconeer XE132",
            "interface": "Enhanced Com Port",
        },
        {  # XE132 ~ as given ...
            "device": "/dev/ttyUSB2",
            "description": "Acconeer XE132 - Standard Com Port",
            "manufacturer": "Silicon Labs",
            "product": "Acconeer XE132",
            "interface": "Standard Com Port",
        },
        {
            "device": "/dev/ttyS5",
        },
        {
            "device": "/dev/ttyS6",
        },
        {
            "device": "/dev/ttyUSB3",
            "description": "Linux Foundation 1.1 root hub ",
        },
    ]
    mock_ports = []
    for mpp in mock_port_attrs:
        lpi = ListPortInfo("")
        for k, v in mpp.items():
            setattr(lpi, k, v)
        mock_ports.append(lpi)
    return mock_ports


def _only_acconeer_devices(tagged_port_infos):
    return [tagged for tagged in tagged_port_infos if tagged[1]]


def test_port_tagging_keeps_all_ports(mock_comports):
    tagged_ports = utils.tag_serial_ports(mock_comports)
    assert len(mock_comports) == len(tagged_ports)


@pytest.mark.parametrize("pyserial_version", ["3.4", "3.5"])
def test_port_tagging_finds_all_acconeer_devices(mock_comports, pyserial_version, mocker):
    expected = 2
    mocker.patch.object(serial, "__version__", pyserial_version)
    if pyserial_version == "3.4":
        # Emulate behaviour of pyserial==3.4 regardless of actual version
        mock_comports[2].interface = None
        mock_comports[3].interface = None
        mock_comports[2].apply_usb_info()
        mock_comports[3].apply_usb_info()
        expected = 3
    tagged_ports = utils.tag_serial_ports(mock_comports)
    only_acconeer = _only_acconeer_devices(tagged_ports)
    assert len(only_acconeer) == expected
