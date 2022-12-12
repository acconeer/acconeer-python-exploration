# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, List, Optional, Type, Union

import attrs

import acconeer.exptool as et
from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.mediators import (
    AgnosticClient,
    BufferedLink,
    ClientBase,
    ClientError,
    CommunicationProtocol,
    Recorder,
)
from acconeer.exptool.a121._rate_calc import _RateStats
from acconeer.exptool.utils import SerialDevice, USBDevice  # type: ignore[import]

from .exploration_protocol import ExplorationProtocol, get_exploration_protocol, messages
from .links import AdaptedSerialLink, AdaptedSocketLink, AdaptedUSBLink, NullLink, NullLinkError


def _get_one_serial_device() -> SerialDevice:
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
        return str(_get_one_serial_device().port)
    else:
        return serial_port


def _get_one_usb_device(only_accessible: bool = False) -> USBDevice:
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
        return _get_one_usb_device(only_accessible=True)
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


class Client(ClientBase):
    _protocol_overridden: bool
    _real_client: ClientBase

    def __init__(
        self,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool, et.utils.USBDevice]] = None,
        override_baudrate: Optional[int] = None,
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ):
        if len([e for e in [ip_address, serial_port, usb_device] if e is not None]) > 1:
            raise ValueError("Only one connection can be selected")

        if isinstance(usb_device, str):
            usb_device = et.utils.get_usb_device_by_serial(usb_device, only_accessible=False)

        if isinstance(usb_device, bool):
            if usb_device:
                usb_device = _get_one_usb_device()
            else:
                raise ValueError("usb_device=False is not valid")

        protocol: Type[CommunicationProtocol] = ExplorationProtocol
        self._protocol_overridden = False

        if _override_protocol is not None:
            protocol = _override_protocol
            self._protocol_overridden = True

        client_info = ClientInfo(
            ip_address=ip_address,
            override_baudrate=override_baudrate,
            serial_port=serial_port,
            usb_device=usb_device,
        )

        self._real_client = AgnosticClient(
            client_info=client_info, link=link_factory(client_info), protocol=protocol
        )

    def connect(self) -> None:
        # This function extends ``AgnosticClient.connect`` by adding a prologue and epilogue.
        # Prologue:
        # 1. If no ``__init__``-arguments was passed (ip_address, serial_port, etc.), tries
        #    to autodetermine a SERIAL or USB link by looking at serial ports, usb devices, etc..
        #
        # runs ``AgnosticClient.connect``
        #
        # Epilogue:
        # 1. Handles a hot-swap of protocol based on the (now) connected server's version.
        # 2. if applicable: sets the overriden baudrate
        if isinstance(self._real_client, AgnosticClient):
            try:
                self._real_client.connect()
            except NullLinkError:
                self._real_client._client_info = autodetermine_client_link(
                    self._real_client._client_info
                )
                self._real_client._link = link_factory(self._real_client.client_info)
                self._real_client.connect()

            if not self._protocol_overridden:
                self._update_protocol_based_on_servers_rss_version()

                self._update_baudrate()
        else:
            raise ClientError("Unknown client type")

    def __enter__(self) -> Client:
        self._real_client.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self._real_client.disconnect()

    def _update_protocol_based_on_servers_rss_version(self) -> None:
        if isinstance(self._real_client, AgnosticClient):
            if issubclass(self._real_client._protocol, ExplorationProtocol):
                try:
                    new_protocol = get_exploration_protocol(self.server_info.parsed_rss_version)
                except Exception:
                    self.disconnect()
                    raise
                else:
                    self._real_client._protocol = new_protocol

    def _update_baudrate(self) -> None:
        if not isinstance(self._real_client, AgnosticClient):
            return

        # Only Change baudrate for AdaptedSerialLink
        if not isinstance(self._real_client._link, AdaptedSerialLink):
            return

        DEFAULT_BAUDRATE = 115200
        overridden_baudrate = self.client_info.override_baudrate
        max_baudrate = self.server_info.max_baudrate
        baudrate_to_use = self.server_info.max_baudrate or DEFAULT_BAUDRATE

        # Override baudrate?
        if overridden_baudrate is not None and max_baudrate is not None:
            # Valid Baudrate?
            if overridden_baudrate > max_baudrate:
                raise ClientError(f"Cannot set a baudrate higher than {max_baudrate}")
            elif overridden_baudrate < DEFAULT_BAUDRATE:
                raise ClientError(f"Cannot set a baudrate lower than {DEFAULT_BAUDRATE}")
            baudrate_to_use = overridden_baudrate

        # Do not change baudrate if DEFAULT_BAUDRATE
        if baudrate_to_use == DEFAULT_BAUDRATE:
            return

        if isinstance(self._real_client, AgnosticClient):
            self._real_client._link.send(
                self._real_client._protocol.set_baudrate_command(baudrate_to_use)
            )

            self._real_client._apply_messages_until_message_type_encountered(
                messages.SetBaudrateResponse
            )
            self._baudrate_ack_received = False

            self._real_client._link.baudrate = baudrate_to_use

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        return self._real_client.setup_session(config, calibrations)

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        self._real_client.start_session(recorder)

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        return self._real_client.get_next()

    def stop_session(self) -> Any:
        return self._real_client.stop_session()

    def disconnect(self) -> None:
        self._real_client.disconnect()

    @property
    def connected(self) -> bool:
        return self._real_client.connected

    @property
    def session_is_setup(self) -> bool:
        return self._real_client.session_is_setup

    @property
    def session_is_started(self) -> bool:
        return self._real_client.session_is_started

    @property
    def server_info(self) -> ServerInfo:
        return self._real_client.server_info

    @property
    def client_info(self) -> ClientInfo:
        return self._real_client.client_info

    @property
    def session_config(self) -> SessionConfig:
        return self._real_client.session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        return self._real_client.extended_metadata

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        return self._real_client.calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        return self._real_client.calibrations_provided

    @property
    def _rate_stats(self) -> _RateStats:
        return self._real_client._rate_stats
