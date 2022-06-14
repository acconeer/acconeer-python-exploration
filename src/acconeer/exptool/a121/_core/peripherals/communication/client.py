from __future__ import annotations

from typing import Optional

import attrs

import acconeer.exptool as et
from acconeer.exptool.a121._core.entities import ClientInfo
from acconeer.exptool.a121._core.mediators import AgnosticClient, BufferedLink, ClientError

from .exploration_protocol import ExplorationProtocol
from .links import AdaptedSerialLink, AdaptedSocketLink, NullLink, NullLinkError


def determine_serial_port(serial_port: Optional[str]) -> str:
    if serial_port is None:
        tagged_ports = et.utils.get_tagged_serial_ports()  # type: ignore[attr-defined]
        A121_TAGS = ["XC120"]
        hopefully_a_single_tagged_port = [port for port, tag in tagged_ports if tag in A121_TAGS]
        try:
            (port,) = hopefully_a_single_tagged_port
            return str(port)
        except ValueError:
            if hopefully_a_single_tagged_port == []:
                raise ClientError("No devices detected. Cannot auto detect.")
            else:
                port_list = "\n".join(
                    [f"* {port} ({tag})" for port, tag in hopefully_a_single_tagged_port]
                )

                raise ClientError(
                    "There are multiple devices detected. Specify one:\n" + port_list
                )
    else:
        return serial_port


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

    return NullLink()


class Client(AgnosticClient):
    _client_info: ClientInfo

    def __init__(
        self,
        ip_address: Optional[str] = None,
        serial_port: Optional[str] = None,
        override_baudrate: Optional[int] = None,
    ):
        if ip_address is not None and serial_port is not None:
            raise ValueError(
                f"Both 'ip_address' ({ip_address}) and 'serial_port' ({serial_port}) "
                + "are not allowed. Chose one."
            )
        self._client_info = ClientInfo(
            ip_address=ip_address,
            override_baudrate=override_baudrate,
            serial_port=serial_port,
        )

        # "protocol"-ignore comes from an unresolved bug in mypy as of 22/04/22
        # [https://github.com/python/mypy/issues/4536]
        super().__init__(
            link=link_factory(self._client_info),
            protocol=ExplorationProtocol,
        )

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info

    def connect(self) -> None:
        try:
            super().connect()
        except NullLinkError:
            self._client_info = attrs.evolve(
                self._client_info, serial_port=determine_serial_port(self.client_info.serial_port)
            )
            self._link = link_factory(self.client_info)
            super().connect()
