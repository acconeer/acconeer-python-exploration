from typing import Optional

from acconeer.exptool.a121._core.entities import ClientInfo
from acconeer.exptool.a121._core.mediators import AgnosticClient, BufferedLink

from .exploration_protocol import ExplorationProtocol
from .links import AdaptedSerialLink, AdaptedSocketLink


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

    raise ValueError(f"Could not construct a suitable link with arguments {client_info}")


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
            protocol=ExplorationProtocol,  # type: ignore[arg-type]
        )

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info
