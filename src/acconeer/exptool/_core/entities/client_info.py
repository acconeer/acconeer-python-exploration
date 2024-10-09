# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import abc
import json
from typing import Any, ClassVar, List, Optional, Type, Union

import attrs

from acconeer.exptool._core.class_creation.formatting import pretty_dict_line_strs


class ClientInfoCreationError(Exception):
    pass


@attrs.frozen(slots=False)
class ConnectionTypeBase(abc.ABC):
    __registry: ClassVar[List[Type[ConnectionTypeBase]]] = []

    @classmethod
    def _register(cls, subclass: Type[ConnectionTypeBase]) -> Type[ConnectionTypeBase]:
        """Registers a subclass"""
        if not issubclass(subclass, cls):
            msg = f"{subclass.__name__!r} needs to be a subclass of {cls.__name__}."
            raise TypeError(msg)
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
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
    ) -> ClientInfo: ...

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
@attrs.frozen(kw_only=True, slots=False)
class SerialInfo(ConnectionTypeBase):
    port: str
    override_baudrate: Optional[int] = None
    serial_number: Optional[str] = None
    flow_control: bool = True

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
    ) -> ClientInfo:
        if serial_port is not None:
            return ClientInfo(
                serial=SerialInfo(
                    port=serial_port,
                    override_baudrate=override_baudrate,
                    flow_control=flow_control,
                )
            )

        raise ClientInfoCreationError()

    @property
    def serial(self) -> SerialInfo:
        return self


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True, slots=False)
class USBInfo(ConnectionTypeBase):
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
    ) -> ClientInfo:
        if usb_device is not None:
            if isinstance(usb_device, bool):
                if usb_device:
                    return ClientInfo(usb=USBInfo())
                msg = "usb_device=False is not valid"
                raise ValueError(msg)

            if isinstance(usb_device, str):
                return ClientInfo(usb=USBInfo(serial_number=usb_device))

        raise ClientInfoCreationError()

    @property
    def usb(self) -> USBInfo:
        return self


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True, slots=False)
class SocketInfo(ConnectionTypeBase):
    ip_address: str
    tcp_port: Optional[int]

    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
    ) -> ClientInfo:
        if ip_address is not None:
            return ClientInfo(socket=SocketInfo(ip_address=ip_address, tcp_port=tcp_port))

        raise ClientInfoCreationError()

    @property
    def socket(self) -> SocketInfo:
        return self


@ConnectionTypeBase._register
@attrs.frozen(kw_only=True, slots=True)
class MockInfo(ConnectionTypeBase):
    @classmethod
    def _from_open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
    ) -> ClientInfo:
        if mock is not None:
            if mock:
                return ClientInfo(mock=MockInfo())

            msg = "mock=False is not valid"
            raise ValueError(msg)

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
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
    ) -> ClientInfo:
        client_info = None
        for subclass in ConnectionTypeBase._get_subclasses():
            try:
                client_info = subclass._from_open(
                    ip_address=ip_address,
                    tcp_port=tcp_port,
                    serial_port=serial_port,
                    usb_device=usb_device,
                    mock=mock,
                    override_baudrate=override_baudrate,
                    flow_control=flow_control,
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

    @staticmethod
    def _migrate_pre_v6_dict(d: dict[str, Any]) -> dict[str, Any]:
        ip_address = d.get("ip_address")
        serial_port = d.get("serial_port")
        usb_device = d.get("usb_device")

        return {
            "mock": {} if d.get("mock", False) else None,
            "socket": (
                None
                if ip_address is None
                else {
                    "ip_address": ip_address,
                    "tcp_port": d.get("tcp_port"),
                }
            ),
            "serial": (
                None
                if serial_port is None
                else {
                    "port": serial_port,
                    "override_baudrate": d.get("override_baudrate"),
                }
            ),
            "usb": (
                None
                if usb_device is None
                else {
                    "vid": usb_device["vid"],
                    "pid": usb_device["pid"],
                    "serial_number": usb_device["serial"],
                }
            ),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientInfo:
        v6_keys = ["socket", "serial", "usb", "mock"]
        v5_keys = [
            "ip_address",
            "tcp_port",
            "serial_port",
            "usb_device",
            "mock",
            "override_baudrate",
        ]

        if not set(d.keys()).issubset(v6_keys):
            d_extra_keys = {k for k in d if k not in v5_keys}
            if d_extra_keys == set():
                d_only_v5_keys = {k: d.get(k) for k in v5_keys}
                d = cls._migrate_pre_v6_dict(d_only_v5_keys)
            else:
                msg = f"Cannot load the dict {d} into a ClientInfo."
                raise TypeError(msg)

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
