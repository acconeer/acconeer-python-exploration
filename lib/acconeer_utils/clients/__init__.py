from .reg.client import RegClient as UARTClient
from .reg.client import RegSPIClient as SPIClient
from .json.client import JSONClient as SocketClient
from .mock.client import MockClient


__all__ = [
    UARTClient,
    SPIClient,
    SocketClient,
    MockClient,
]
