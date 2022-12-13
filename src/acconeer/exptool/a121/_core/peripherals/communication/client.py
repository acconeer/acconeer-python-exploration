# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Optional, Type, Union

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
from acconeer.exptool.a121._core.mediators import ClientBase, Recorder
from acconeer.exptool.a121._rate_calc import _RateStats

from .communication_protocol import CommunicationProtocol
from .exploration_client import ExplorationClient
from .mock_client import MockClient
from .utils import get_one_usb_device


class Client(ClientBase):
    _protocol_overridden: bool
    _real_client: ClientBase

    def __init__(
        self,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool, et.utils.USBDevice]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ):
        if len([e for e in [ip_address, serial_port, usb_device, mock] if e is not None]) > 1:
            raise ValueError("Only one connection can be selected")

        if mock is not None:
            if mock:
                client_info = ClientInfo(
                    mock=mock,
                )
                self._real_client = MockClient(client_info=client_info)
            else:
                raise ValueError("mock=False is not valid")
        else:
            if isinstance(usb_device, str):
                usb_device = et.utils.get_usb_device_by_serial(usb_device, only_accessible=False)

            if isinstance(usb_device, bool):
                if usb_device:
                    usb_device = get_one_usb_device()
                else:
                    raise ValueError("usb_device=False is not valid")

            client_info = ClientInfo(
                ip_address=ip_address,
                override_baudrate=override_baudrate,
                serial_port=serial_port,
                usb_device=usb_device,
            )

            self._real_client = ExplorationClient(
                client_info=client_info,
                _override_protocol=_override_protocol,
            )

    def connect(self) -> None:
        self._real_client.connect()

    def __enter__(self) -> Client:
        self._real_client.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self._real_client.disconnect()

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
