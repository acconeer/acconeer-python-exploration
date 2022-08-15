# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Optional, Tuple, Union

import numpy as np

import acconeer.exptool as et

from .client_factory import ClientFactory
from .common import Link, LinkArg, ProtocolArg
from .json.client import SocketClient
from .mock.client import MockClient
from .reg.client import SPIClient, UARTClient


class Client:
    def __init__(
        self,
        *,
        protocol: Optional[ProtocolArg] = None,
        link: Optional[LinkArg] = None,
        mock: bool = False,
        **kwargs: Any,
    ):
        """
        :param protocol:
            What protocol the client is supposed to use. Can be any :class:`.Protocol`
            member or their ``str``-counterparts.
            ``protocol=None`` (default) will try to auto-detect.

        :param link:
            What link the client is supposed to use. Can be any :class:`.Link`
            member or their ``str```-counterparts.
            ``link=None`` (default) will try to auto-detect.

        :param mock:
            Whether this Client should be a simulated client.

        :param kwargs:
            These are the supported kwargs:

            | **host:** str
            |   IP-address of e.g. the RBPi you want to connect to.

            | **serial_port:** str
            |   The serial port name. E.g. ``COMx`` on Windows and ``/dev/ttyUSBx`` on Linux.

            | **override_baudrate:** int
            |   Uses the passed baudrate instead of the default.

        :raises: ValueError if a ``Client`` could not be created from the arguments.
        """
        if mock:
            self.subclient = MockClient()
        else:
            self.subclient = ClientFactory.from_kwargs(protocol=protocol, link=link, **kwargs)

    def get_link_type(self) -> Union[Link, str]:
        if isinstance(self.subclient, MockClient):
            return "mock"
        elif isinstance(self.subclient, UARTClient):
            return Link.UART
        elif isinstance(self.subclient, SPIClient):
            return Link.SPI
        elif isinstance(self.subclient, SocketClient):
            return Link.SOCKET
        else:
            raise ValueError(f"Unknown subclient type: {type(self.subclient)}")

    def connect(self) -> dict:
        """Initiates a connection with the device.

        :return: A dict containing information about the device, including SDK version
        """
        return self.subclient.connect()

    def setup_session(
        self, config: et.a111._configs.BaseSessionConfig, check_config: bool = True
    ) -> dict:
        """
        Sets up a session with the given config.
        Will call ``connect()`` if not already connected.

        :param config: The configuration to use when setting up the session
        :param check_config: If `True` the configuration is checked for errors,
                            defaults to `True`

        :return: A dict with metadata for the configured session
        """
        return self.subclient.setup_session(config, check_config)

    def start_session(
        self,
        config: Optional[et.a111._configs.BaseSessionConfig] = None,
        check_config: bool = True,
    ) -> Optional[dict]:
        """
        Starts the session if previously set up with ``setup_session()``.
        If `config` is provided, ``setup_session()`` will be called.

        :param config: The configuration to use when setting up the session, defaults to `None`
        :param check_config: If `True` the configuration is checked for errors,
                            defaults to `True`

        :return: If `config` is provided, returns a dict with metadata for the configured session.
                Otherwise, returns `None`
        """
        return self.subclient.start_session(config, check_config)

    def get_next(self) -> Tuple[Union[list, dict], np.ndarray]:
        """
        Retrieves the next result. Will block until the result is received.

        :return: A tuple with the result info and data.
                The data shape and type differs between services.

                | **Power Bins:**
                | Shape: (number of sensors, bin count)
                | Type: float64

                | **Envelope:**
                | Shape: (number of sensors, data length)
                | Type: float64

                | **IQ:**
                | Shape: (number of sensors, data length)
                | Type: complex128

                | **Sparse:**
                | Shape: (number of sensors, number of sweeps, number of depths)
                | Type: float64

                `Number of sensors`, `bin count` and `number of sweeps` can be explicitly set.
                `Data length` and `number of dephts` depend on multiple configuration settings.

                The client takes a parameter ``squeeze``, if set to `True` the first
                dimension (`number of sensors`) is removed when using a single sensor.
                As default ``squeeze`` is  `True`.
        """
        return self.subclient.get_next()

    def stop_session(self):
        """
        Stops the session. All buffered/waiting data is thrown away.
        This function will block until the server has confirmed that the session has ended.
        """
        self.subclient.stop_session()

    def disconnect(self):
        """
        Disconnects the client. ``disconnect()`` will call ``stop_session()``
        if a session is started.
        """
        self.subclient.disconnect()

    @property
    def supported_modes(self):
        return self.subclient.supported_modes

    @property
    def squeeze(self):
        return self.subclient.squeeze

    @squeeze.setter
    def squeeze(self, squeeze):
        self.subclient.squeeze = squeeze

    @property
    def description(self) -> str:
        return self.subclient.description
