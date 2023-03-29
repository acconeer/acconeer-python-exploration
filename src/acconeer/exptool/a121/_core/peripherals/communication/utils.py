# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import List, Optional

import attrs

import acconeer.exptool as et
from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    SensorCalibration,
    SerialInfo,
    SessionConfig,
    USBInfo,
)
from acconeer.exptool.a121._core.mediators import BufferedLink
from acconeer.exptool.a121._core.utils import iterate_extended_structure
from acconeer.exptool.utils import SerialDevice, USBDevice  # type: ignore[import]

from .common_client import ClientError
from .links import AdaptedSerialLink, AdaptedSocketLink, AdaptedUSBLink, NullLink


def get_one_serial_device() -> SerialDevice:
    acconeer_serial_devices: List[SerialDevice] = [
        device for device in et.utils.get_serial_devices() if device.name is not None
    ]

    if not acconeer_serial_devices:
        raise ClientError("No serial devices detected. Cannot auto detect.")
    elif len(acconeer_serial_devices) > 1:
        devices_string = "".join([f" - {dev}\n" for dev in acconeer_serial_devices])
        raise ClientError("There are multiple devices detected. Specify one:\n" + devices_string)
    else:
        return acconeer_serial_devices[0]


def get_one_usb_device(only_accessible: bool = False) -> USBDevice:
    usb_devices = et.utils.get_usb_devices(only_accessible=only_accessible)
    if not usb_devices:
        raise ClientError("No USB devices detected. Cannot auto detect.")
    elif len(usb_devices) > 1:
        devices_string = "".join([f" - {dev}\n" for dev in usb_devices])
        raise ClientError("There are multiple devices detected. Specify one:\n" + devices_string)
    else:
        return usb_devices[0]


def link_factory(client_info: ClientInfo) -> BufferedLink:

    if client_info.socket is not None:
        return AdaptedSocketLink(
            host=client_info.socket.ip_address, port=client_info.socket.tcp_port
        )

    if client_info.serial is not None:
        return AdaptedSerialLink(
            port=client_info.serial.port,
        )

    if client_info.usb is not None:
        usb_device = None
        if client_info.usb.serial_number is not None:
            usb_device = et.utils.get_usb_device_by_serial(
                client_info.usb.serial_number, only_accessible=False
            )
        else:
            usb_device = get_one_usb_device()

        if usb_device is not None:
            return AdaptedUSBLink(
                vid=usb_device.vid,
                pid=usb_device.pid,
                serial=usb_device.serial,
            )

    return NullLink()


def autodetermine_client_link(client_info: ClientInfo) -> ClientInfo:
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

    except ClientError as exc:
        error_message += f"\nUSB: {str(exc)}"
        pass

    try:
        serial_info = client_info.serial
        if serial_info is None:
            serial_info = SerialInfo(port=str(get_one_serial_device().port))
        return attrs.evolve(client_info, serial=serial_info)
    except ClientError as exc:
        error_message += f"\nSerial: {str(exc)}"

    raise ClientError(f"Cannot auto detect:{error_message}")


def get_calibrations_provided(
    session_config: SessionConfig,
    calibrations: Optional[dict[int, SensorCalibration]] = None,
) -> dict[int, bool]:
    calibrations_provided = {}
    for _, sensor_id, _ in iterate_extended_structure(session_config.groups):
        if calibrations:
            calibrations_provided[sensor_id] = sensor_id in calibrations
        else:
            calibrations_provided[sensor_id] = False

    return calibrations_provided
