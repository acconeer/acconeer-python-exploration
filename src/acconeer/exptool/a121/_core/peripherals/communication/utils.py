# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import List, Optional

import attrs

import acconeer.exptool as et
from acconeer.exptool.a121._core.entities import ClientInfo, SensorCalibration, SessionConfig
from acconeer.exptool.a121._core.mediators import BufferedLink, ClientError
from acconeer.exptool.a121._core.utils import iterate_extended_structure
from acconeer.exptool.utils import SerialDevice, USBDevice  # type: ignore[import]

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


def determine_serial_device(serial_port: Optional[str]) -> str:
    if serial_port is None:
        return str(get_one_serial_device().port)
    else:
        return serial_port


def get_one_usb_device(only_accessible: bool = False) -> USBDevice:
    usb_devices = et.utils.get_usb_devices(only_accessible=only_accessible)
    if not usb_devices:
        raise ClientError("No USB devices detected. Cannot auto detect.")
    elif len(usb_devices) > 1:
        devices_string = "".join([f" - {dev}\n" for dev in usb_devices])
        raise ClientError("There are multiple devices detected. Specify one:\n" + devices_string)
    else:
        return usb_devices[0]


def determine_usb_device(usb_device: Optional[USBDevice]) -> USBDevice:
    if usb_device is None:
        return get_one_usb_device(only_accessible=True)
    else:
        return usb_device


def link_factory(client_info: ClientInfo) -> BufferedLink:

    if client_info.ip_address is not None:
        return AdaptedSocketLink(host=client_info.ip_address)

    if client_info.serial_port is not None:
        link = AdaptedSerialLink(
            port=client_info.serial_port,
        )

        return link

    if client_info.usb_device is not None:
        link = AdaptedUSBLink(
            vid=client_info.usb_device.vid,
            pid=client_info.usb_device.pid,
            serial=client_info.usb_device.serial,
        )

        return link

    return NullLink()


def autodetermine_client_link(client_info: ClientInfo) -> ClientInfo:
    error_message = ""
    try:
        client_info = attrs.evolve(
            client_info,
            usb_device=determine_usb_device(client_info.usb_device),
        )

        return client_info
    except ClientError as exc:
        error_message += f"\nUSB: {str(exc)}"
        pass

    try:
        client_info = attrs.evolve(
            client_info,
            serial_port=determine_serial_device(client_info.serial_port),
        )
        return client_info
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
