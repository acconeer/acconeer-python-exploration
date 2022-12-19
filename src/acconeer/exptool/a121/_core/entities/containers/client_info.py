# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
import json
from typing import Any, List, Optional, Type, Union

import attrs

from acconeer.exptool.a121._core.utils import pretty_dict_line_strs


class ClientInfoCreationError(Exception):
    pass


class ConnectionTypeBase(abc.ABC):

    __registry: List[Type[ConnectionTypeBase]] = []

    @classmethod
    def _register(cls, subclass: Type[ConnectionTypeBase]) -> Type[ConnectionTypeBase]:
        """Registers a subclass"""
        if not issubclass(subclass, cls):
            raise TypeError(f"{subclass.__name__!r} needs to be a subclass of {cls.__name__}.")
        cls.__registry.append(subclass)
        return subclass

    @classmethod
    def _get_subclasses(cls) -> List[Type[ConnectionTypeBase]]:
        return cls.__registry

    @classmethod
    @abc.abstractmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
    ) -> ClientInfo:
        ...

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @property
    def serial(self) -> Optional[SerialInfo]:
        return None

    @property
    def usb(self) -> Optional[USBInfo]:
        return None

    @property
    def socket(self) -> Optional[SocketInfo]:
        return None

    @property
    def mock(self) -> Optional[MockInfo]:
        return None


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True)
class SerialInfo(ConnectionTypeBase):
    port: str
    override_baudrate: Optional[int] = None
    serial_number: Optional[str] = None

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
    ) -> ClientInfo:
        if serial_port is not None:
            return ClientInfo(
                serial=SerialInfo(port=serial_port, override_baudrate=override_baudrate)
            )

        raise ClientInfoCreationError()

    @property
    def serial(self) -> SerialInfo:
        return self


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True)
class USBInfo(ConnectionTypeBase):
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
    ) -> ClientInfo:
        if usb_device is not None:
            if isinstance(usb_device, bool):
                if usb_device:
                    return ClientInfo(usb=USBInfo())
                raise ValueError("usb_device=False is not valid")

            if isinstance(usb_device, str):
                return ClientInfo(usb=USBInfo(serial_number=usb_device))

        raise ClientInfoCreationError()

    @property
    def usb(self) -> USBInfo:
        return self


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True)
class SocketInfo(ConnectionTypeBase):
    ip_address: str

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
    ) -> ClientInfo:
        if ip_address is not None:
            return ClientInfo(socket=SocketInfo(ip_address=ip_address))

        raise ClientInfoCreationError()

    @property
    def socket(self) -> SocketInfo:
        return self


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True)
class MockInfo(ConnectionTypeBase):
    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
    ) -> ClientInfo:
        if mock is not None:
            if mock:
                return ClientInfo(mock=MockInfo())

            raise ValueError("mock=False is not valid")

        raise ClientInfoCreationError()

    @property
    def mock(self) -> MockInfo:
        return self


@attrs.frozen(kw_only=True)
class ClientInfo:
    socket: Optional[SocketInfo] = None
    serial: Optional[SerialInfo] = None
    usb: Optional[USBInfo] = None
    mock: Optional[MockInfo] = None

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
    ) -> ClientInfo:
        client_info = None
        for subclass in ConnectionTypeBase._get_subclasses():
            try:
                client_info = subclass._from_open(
                    ip_address=ip_address,
                    serial_port=serial_port,
                    usb_device=usb_device,
                    mock=mock,
                    override_baudrate=override_baudrate,
                )
                break
            except ClientInfoCreationError:
                pass

        if client_info is not None:
            return client_info

        # Return empyt ClientInfo if everything is None
        return ClientInfo()

    def to_dict(self) -> dict[str, Any]:
        return attrs.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ClientInfo:
        for arg in d:
            if arg not in ["socket", "serial", "usb", "mock"]:
                raise TypeError()
        serial = SerialInfo(**d["serial"]) if d.get("serial") is not None else None
        usb = USBInfo(**d["usb"]) if d.get("usb") is not None else None
        socket = SocketInfo(**d["socket"]) if d.get("socket") is not None else None
        mock = MockInfo(**d["mock"]) if d.get("mock") is not None else None
        return cls(
            socket=socket,
            serial=serial,
            usb=usb,
            mock=mock,
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> ClientInfo:
        return cls.from_dict(json.loads(json_str))

    def __str__(self) -> str:
        return "\n".join(
            [
                f"{type(self).__name__}",
                *pretty_dict_line_strs(self.to_dict()),
            ]
        )
