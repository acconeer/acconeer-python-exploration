# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import platform
from typing import Optional, Type, Union

import attrs

import acconeer.exptool as et
from acconeer.exptool.a121._core.entities import ClientInfo
from acconeer.exptool.a121._core.mediators import (
    AgnosticClient,
    BufferedLink,
    ClientError,
    CommunicationProtocol,
)
from acconeer.exptool.utils import USBDevice  # type: ignore[import]

from .exploration_protocol import ExplorationProtocol, get_exploration_protocol
from .links import AdaptedSerialLink, AdaptedSocketLink, AdaptedUSBLink, NullLink, NullLinkError


def determine_serial_port(serial_port: Optional[str]) -> str:
    if serial_port is None:
        tagged_ports = et.utils.get_tagged_serial_ports()
        A121_TAGS = ["XC120"]
        hopefully_a_single_tagged_port = [port for port, tag in tagged_ports if tag in A121_TAGS]
        try:
            (port,) = hopefully_a_single_tagged_port
            return str(port)
        except ValueError:
            if hopefully_a_single_tagged_port == []:
                raise ClientError("No serial devices detected. Cannot auto detect.")
            else:
                port_list = "\n".join(
                    [f"* {port} ({tag})" for port, tag in hopefully_a_single_tagged_port]
                )

                raise ClientError(
                    "There are multiple devices detected. Specify one:\n" + port_list
                )
    else:
        return serial_port


def determine_usb_device(usb_device: Optional[USBDevice]) -> USBDevice:
    if usb_device is None:
        usb_devices = et.utils.get_usb_devices()

        if not usb_devices:
            raise ClientError("No USB devices detected. Cannot auto detect.")
        elif len(usb_devices) > 1:
            raise ClientError("There are multiple devices detected. Specify one:\n" + usb_devices)
        else:
            return usb_devices[0]
    else:
        return usb_device


def link_factory(client_info: ClientInfo) -> BufferedLink:

    if client_info.ip_address is not None:
        return AdaptedSocketLink(host=client_info.ip_address)

    if client_info.serial_port is not None:
        link = AdaptedSerialLink(
            port=client_info.serial_port,
        )
        if client_info.override_baudrate is not None:
            link.baudrate = client_info.override_baudrate

        return link

    if client_info.usb_device is not None:
        link = AdaptedUSBLink(
            vid=client_info.usb_device.vid,
            pid=client_info.usb_device.pid,
            name=client_info.usb_device.name,
        )

        return link

    return NullLink()


def autodetermine_client_link(client_info: ClientInfo) -> ClientInfo:
    if platform.system().lower() == "windows":
        try:
            client_info = attrs.evolve(
                client_info,
                usb_device=determine_usb_device(client_info.usb_device),
            )

            return client_info
        except ClientError:
            pass
    try:
        client_info = attrs.evolve(
            client_info,
            serial_port=determine_serial_port(client_info.serial_port),
        )
        return client_info
    except ClientError:
        raise ClientError("No devices detected. Cannot auto detect.")


class Client(AgnosticClient):
    _protocol_overridden: bool
    _client_info: ClientInfo

    def __init__(
        self,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, et.utils.USBDevice]] = None,
        override_baudrate: Optional[int] = None,
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ):
        if len([e for e in [ip_address, serial_port, usb_device] if e is not None]) > 1:
            raise ValueError("Only one connection can be selected")

        if isinstance(usb_device, str):
            raise NotImplementedError("Selecting device by serial number not supported")

        protocol: Type[CommunicationProtocol] = ExplorationProtocol
        self._protocol_overridden = False

        if _override_protocol is not None:
            protocol = _override_protocol
            self._protocol_overridden = True

        self._client_info = ClientInfo(
            ip_address=ip_address,
            override_baudrate=override_baudrate,
            serial_port=serial_port,
            usb_device=usb_device,
        )

        super().__init__(
            link=link_factory(self._client_info),
            protocol=protocol,
        )

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info

    def connect(self) -> None:
        try:
            super().connect()
        except NullLinkError:
            self._client_info = autodetermine_client_link(self._client_info)
            self._link = link_factory(self.client_info)
            super().connect()

        if not self._protocol_overridden:
            if issubclass(self._protocol, ExplorationProtocol):
                try:
                    new_protocol = get_exploration_protocol(self.server_info.parsed_rss_version)
                except Exception:
                    self.disconnect()
                    raise
                else:
                    self._protocol = new_protocol
