# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import attrs
from serial.serialutil import SerialException

import acconeer.exptool
from acconeer.exptool._core.communication.comm_devices import (
    CommDeviceError,
    get_one_serial_device,
    get_one_usb_device,
)
from acconeer.exptool._core.entities import (
    ClientInfo,
    SerialInfo,
    USBInfo,
)

from . import (
    BufferedLink,
    ExploreSerialLink,
    LinkError,
    NullLink,
    NullLinkError,
    SocketLink,
    USBLink,
)


def link_factory(client_info: ClientInfo) -> BufferedLink:
    if client_info.socket is not None:
        return SocketLink(host=client_info.socket.ip_address, port=client_info.socket.tcp_port)

    if client_info.serial is not None:
        return ExploreSerialLink(
            port=client_info.serial.port,
            flowcontrol=client_info.serial.flow_control,
        )

    if client_info.usb is not None:
        usb_device = None
        if client_info.usb.serial_number is not None:
            usb_device = (
                acconeer.exptool._core.communication.comm_devices.get_usb_device_by_serial(
                    client_info.usb.serial_number, only_accessible=False
                )
            )
        else:
            usb_device = get_one_usb_device()

        if usb_device is not None:
            return USBLink(
                vid=usb_device.vid,
                pid=usb_device.pid,
                serial=usb_device.serial,
            )

    return NullLink()


def autodetermine_client_info(client_info: ClientInfo) -> ClientInfo:
    error_message = ""
    try:
        usb_info = client_info.usb
        if usb_info is None:
            usb_device = get_one_usb_device(only_accessible=True)
            usb_info = USBInfo(
                vid=usb_device.vid, pid=usb_device.pid, serial_number=usb_device.serial
            )
        return attrs.evolve(
            client_info,
            usb=usb_info,
        )

    except CommDeviceError as exc:
        error_message += f"\nUSB: {str(exc)}"
        pass

    try:
        serial_info = client_info.serial
        if serial_info is None:
            serial_info = SerialInfo(port=str(get_one_serial_device().port))
        return attrs.evolve(client_info, serial=serial_info)
    except CommDeviceError as exc:
        error_message += f"\nSerial: {str(exc)}"

    msg = f"Cannot auto detect:{error_message}"
    raise LinkError(msg)


def ensure_connected_link(client_info: ClientInfo) -> tuple[BufferedLink, ClientInfo]:
    """
    Tries connecting a link defined by the given ClientInfo
    before trying to autodetermine a link which can be used.

    Returns the connected link and a new ClientInfo that describes the connected link.
    """
    link = link_factory(client_info)

    try:
        link.connect()
        return link, client_info
    except NullLinkError:
        new_client_info = autodetermine_client_info(client_info)
        return ensure_connected_link(new_client_info)
    except SerialException as exc:
        if "Permission denied" in str(exc):
            text = "\n".join(
                [
                    "You are probably missing permissions to access the serial port.",
                    "",
                    "Run the setup script to fix it:",
                    "$ python -m acconeer.exptool.setup",
                    "",
                    "Reboot for the changes to take effect.",
                ]
            )
            raise LinkError(text) from exc
        else:
            raise
