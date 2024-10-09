# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import abc
import typing as t

import typing_extensions as te

from acconeer.exptool._core.entities import ClientInfo


_ConfigT = t.TypeVar("_ConfigT")
_MetadataT = t.TypeVar("_MetadataT")
_ResultT = t.TypeVar("_ResultT")
_ServerInfoT = t.TypeVar("_ServerInfoT")


_RecorderT = t.TypeVar("_RecorderT")


class ClientError(Exception):
    pass


class ServerError(Exception):
    pass


class ClientCreationError(Exception):
    pass


class ClientABCWithGoodError(abc.ABC):
    def __new__(cls, *args: t.Any, **kwargs: t.Any) -> ClientABCWithGoodError:
        try:
            return super().__new__(cls)
        except TypeError:  # te here is the "Can't instantiate ..."-error
            if cls == Client:
                msg = "Client cannot be instantiated, use Client.open()"
                raise ClientCreationError(msg) from None
            else:
                raise


class Client(
    ClientABCWithGoodError,
    t.Generic[_ConfigT, _MetadataT, _ResultT, _ServerInfoT, _RecorderT],
):
    __registry: te.Final[list[type]] = []

    def __init__(self, client_info: ClientInfo) -> None:
        self._client_info = client_info

        self._session_is_started = False

        self._recorder: t.Optional[_RecorderT] = None
        self._metadata: t.Optional[_MetadataT] = None

    @classmethod
    def open(
        cls,
        ip_address: t.Optional[str] = None,
        tcp_port: t.Optional[int] = None,
        serial_port: t.Optional[str] = None,
        usb_device: t.Optional[t.Union[str, bool]] = None,
        mock: t.Optional[bool] = None,
        override_baudrate: t.Optional[int] = None,
        flow_control: bool = True,
        generation: t.Optional[str] = None,
    ) -> te.Self:
        """
        Open a new client
        """
        if len([e for e in [ip_address, serial_port, usb_device, mock] if e is not None]) > 1:
            msg = "Only one connection can be selected"
            raise ValueError(msg)

        for subclass in cls.__registry:
            try:
                # For a class to be in the "__registry"-list it needs to be a subclass,
                # which it is since it's added in "__init_subclass__".
                #
                # It will also always have the ".open" classmethod, thanks to MRO.
                #
                # That is why these errors are ignored instead of handled.
                return subclass.open(  # type: ignore[no-any-return, attr-defined]
                    ip_address,
                    tcp_port,
                    serial_port,
                    usb_device,
                    mock,
                    override_baudrate,
                    flow_control,
                    generation,
                )
            except ClientCreationError:
                continue

        # This should not happen since the current implementation
        # only has two clients which are mutual exclusive.
        # * The mock client (mock is not None)
        # * The exploration client (mock is None)
        raise ClientCreationError(
            "No client could be created"
            + (". Try specifying 'generation'" if generation is None else "")
        )

    @classmethod
    def __init_subclass__(cls, *, register: bool, **kwargs: t.Any) -> None:
        """
        Registers a subclass if register == True

        Subclasses specifies whether they should be registered in the
        "inherintance list"; class ClientSubclass(Client, register=True)
        """
        super.__init_subclass__(**kwargs)
        if register:
            cls.__registry.append(cls)

    def attach_recorder(self, recorder: _RecorderT) -> None:
        if self.session_is_started:
            msg = "Cannot attach a recorder when session is started."
            raise ClientError(msg)

        if not self.connected:
            msg = "Cannot attach a recorder to a closed client"
            raise ClientError(msg)

        if self._recorder is not None:
            raise ClientError(
                "Client already has a recorder attached. "
                + "Try detaching the current recorder before attaching a new recorder."
            )

        self._recorder = recorder
        self._recorder_start(recorder)

    @abc.abstractmethod
    def _recorder_start(self, recorder: _RecorderT) -> None: ...

    @abc.abstractmethod
    def _recorder_start_session(self) -> None: ...

    @abc.abstractmethod
    def _recorder_sample(self, result: _ResultT) -> None: ...

    @abc.abstractmethod
    def _recorder_stop_session(self) -> None: ...

    def detach_recorder(self) -> t.Optional[_RecorderT]:
        if self.session_is_started:
            msg = "Cannot detach a recorder when session is started."
            raise ClientError(msg)

        if not self.connected:
            msg = "Cannot detach a recorder from a closed client"
            raise ClientError(msg)

        if self._recorder is None:
            return None
        else:
            previously_attached_recorder = self._recorder
            self._recorder = None
            return previously_attached_recorder

    @abc.abstractmethod
    def setup_session(self, config: _ConfigT) -> _MetadataT: ...

    @abc.abstractmethod
    def start_session(self) -> None:
        """Starts the already set up session.

        After this call, the server starts streaming data to the client.

        :raises: ``ClientError`` if ``Client``'s  session is not set up.
        """
        ...

    @abc.abstractmethod
    def get_next(self) -> _ResultT: ...

    @abc.abstractmethod
    def stop_session(self) -> None:
        """Stops an on-going session

        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        ...

    @abc.abstractmethod
    def close(self) -> None:
        """Closes the connection to the host"""
        ...

    @property
    @abc.abstractmethod
    def connected(self) -> bool:
        """Whether this Client is connected."""
        ...

    @property
    @abc.abstractmethod
    def server_info(self) -> _ServerInfoT:
        """The ``ServerInfo``."""
        ...

    @property
    def session_is_setup(self) -> bool:
        """Whether this Client has a session set up."""
        return self._metadata is not None

    @property
    def session_is_started(self) -> bool:
        """Whether this Client's session is started."""
        return self._session_is_started

    @property
    def client_info(self) -> ClientInfo:
        """The ``ClientInfo``."""
        return self._client_info

    def _assert_connected(self) -> None:
        if not self.connected:
            msg = "Client is not connected."
            raise ClientError(msg)

    def _assert_session_setup(self) -> None:
        self._assert_connected()
        if not self.session_is_setup:
            msg = "Session is not set up."
            raise ClientError(msg)

    def _assert_session_started(self) -> None:
        self._assert_session_setup()
        if not self.session_is_started:
            msg = "Session is not started."
            raise ClientError(msg)

    def __enter__(self) -> te.Self:
        return self

    def __exit__(self, *_: t.Any) -> None:
        self.close()
