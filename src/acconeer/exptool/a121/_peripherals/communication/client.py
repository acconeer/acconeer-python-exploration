from typing import Optional

from acconeer.exptool.a121 import ClientInfo
from acconeer.exptool.a121._mediators import AgnosticClient, BufferedLink, CommunicationProtocol

from .exploration_protocol import ExplorationProtocol
from .links import AdaptedSerialLink, AdaptedSocketLink


def protocol_factory(client_info: ClientInfo) -> CommunicationProtocol:
    if client_info.protocol == "exploration":
        # Ignore comes from an unresolved bug in mypy as of 22/04/22
        # [https://github.com/python/mypy/issues/4536]
        return ExplorationProtocol  # type: ignore[return-value]

    raise ValueError(f"Could not construct a suitable protocol with arguments {client_info}")


def link_factory(client_info: ClientInfo) -> BufferedLink:

    if client_info.address is not None:
        return AdaptedSocketLink(host=client_info.address)

    if client_info.serial_port is not None:
        link = AdaptedSerialLink(
            port=client_info.serial_port,
        )
        if client_info.override_baudrate is not None:
            link.baudrate = client_info.override_baudrate

        return link

    raise ValueError(f"Could not construct a suitable link with arguments {client_info}")


class Client(AgnosticClient):
    _client_info: ClientInfo

    def __init__(
        self,
        address: Optional[str] = None,
        link: Optional[str] = None,
        override_baudrate: Optional[int] = None,
        protocol: Optional[str] = None,
        serial_port: Optional[str] = None,
    ):
        self._client_info = ClientInfo(
            address=address,
            link=link,
            override_baudrate=override_baudrate,
            protocol=protocol,
            serial_port=serial_port,
        )
        super().__init__(
            link=link_factory(self._client_info), protocol=protocol_factory(self._client_info)
        )

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info
