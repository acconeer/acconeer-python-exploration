# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import acconeer.exptool as et

from .base import BaseClient
from .common import Link, LinkArg, Protocol, ProtocolArg
from .json.client import SocketClient
from .reg.client import SPIClient, UARTClient


class ClientFactory:
    """
    A Factory that sole responsibility is the creation of `BaseClient` subclasses and
    Error handling.
    """

    @classmethod
    def from_kwargs(
        cls,
        *,
        protocol: Optional[ProtocolArg] = None,
        link: Optional[LinkArg] = None,
        **kwargs: Any,
    ) -> BaseClient:
        cls._check_conflicting_kwargs(protocol=protocol, link=link, **kwargs)

        if link is None:
            link = cls._try_infer_link_from_kwargs(**kwargs)

        if protocol is None:
            protocol = cls._try_infer_protocol_from_kwargs(**kwargs)

        if link == Link.UART:
            port = cls._handle_passed_serial_port(kwargs.pop("serial_port", None))
            return cls._try_get_serial_client(port, protocol, **kwargs)

        if link == Link.SOCKET:
            host = cls._handle_passed_host(kwargs.pop("host", None))
            return cls._try_get_socket_client(host, protocol, **kwargs)

        if link == Link.SPI:
            return SPIClient(**kwargs)

        raise ValueError(f"Could not determine client type. Unrecognized link: {link}")

    @classmethod
    def _check_conflicting_kwargs(cls, **kwargs):
        CONFLICTING_KEY_COMBINATIONS = [{"host", "serial_port"}]

        keys_to_check = {k for k, v in kwargs.items() if v is not None}

        for key_combination in CONFLICTING_KEY_COMBINATIONS:
            # "<=" operator between sets is a subset-check.
            if key_combination <= keys_to_check:
                raise ValueError(
                    f"Incompatible keyword-arguments: {key_combination}. "
                    + "These cannot be used together."
                )

    @classmethod
    def _try_infer_link_from_kwargs(cls, **kwargs: Any) -> Link:
        """
        Tries to figure out what link to use from `kwargs`. E.g.
        if "host" is supplied, then link=Links.SOCKET can be inferred.
        """
        if kwargs.get("host"):
            return Link.SOCKET

        return Link.UART

    @classmethod
    def _try_infer_protocol_from_kwargs(cls, **_: Any) -> Optional[Protocol]:
        """
        Tries to figure out what protocols to use from `kwargs`.
        """

        # Ready for extension
        return None

    @classmethod
    def _try_get_socket_client(
        cls, host: str, protocol: Optional[ProtocolArg], **kwargs: Any
    ) -> BaseClient:
        """
        Tries to create a socket client given the passed `protocol` and `kwargs`.

        :raises: ValueError if it fails somewhere along the way.
        """

        if protocol == Protocol.EXPLORATION or protocol == Protocol.STREAMING or protocol is None:
            # SocketClient auto-detects the protocol.
            return SocketClient(host, **kwargs)
        else:
            raise ValueError(
                f"Could not determine client type. link=socket, protocol={protocol}, host={host}"
            )

    @classmethod
    def _try_get_serial_client(
        cls, port: str, protocol: Optional[ProtocolArg], **kwargs: Any
    ) -> BaseClient:
        """
        Tries to create a serial/uart client given `protocol`, `port` and `kwargs`.

        :raises: ValueError if it fails somewhere along the way.
        """
        if protocol == Protocol.MODULE:
            return UARTClient(port, **kwargs)

        if protocol == Protocol.EXPLORATION:
            return SocketClient(host=port, serial_link=True, **kwargs)

        raise ValueError(
            f"Could not determine client type. link=serial, protocol={protocol}, port={port}"
        )

    @classmethod
    def _handle_passed_host(cls, host: Optional[str]) -> str:
        """
        :raises: ValueError if `host` is None.
        """
        if host is None:
            raise ValueError(
                "Clients that communicate over sockets need a host. Please specify a host with"
                + '"host=<your host>" to "Client"'
            )

        return host

    @classmethod
    def _handle_passed_serial_port(cls, serial_port: Optional[str]) -> str:
        """
        If `serial_port` is None, tries to get a port from auto-detection.

        :raises: ValueError if `serial_port` is None and the number of auto-detected ports != 1.
        """
        if serial_port is None:
            return cls._get_single_acconeer_module_port(et.utils.get_tagged_serial_ports())

        return serial_port

    @classmethod
    def _get_single_acconeer_module_port(cls, tagged_ports: List[Tuple[str, str]]):
        """
        Auto-detects Acconeer modules for use in this factory.

        :raises: ValueError if the number of auto-detected modules is not exactly 1.
        """
        acconeer_module_ports = [port for port, tag in tagged_ports if tag is not None]

        if len(acconeer_module_ports) > 1:
            raise ValueError(
                "Multiple Acconeer modules are connected. Please specify a single port with"
                + '"serial_port=<your serial port>" to "Client"'
            )

        if len(acconeer_module_ports) == 0:
            raise ValueError("Could not auto-detect any Acconeer modules.")

        return acconeer_module_ports[0]
