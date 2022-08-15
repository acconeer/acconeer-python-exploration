# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Tuple, Type, Union

import attrs

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.utils import (
    create_extended_structure,
    iterate_extended_structure,
    unextend,
    unwrap_ticks,
)
from acconeer.exptool.a121._perf_calc import _PerformanceCalc

from .communication_protocol import CommunicationProtocol
from .link import BufferedLink
from .recorder import Recorder


log = logging.getLogger(__name__)


class ClientError(Exception):
    pass


class AgnosticClient:
    _link: BufferedLink
    _default_link_timeout: float
    _link_timeout: float
    _protocol: Type[CommunicationProtocol]
    _server_info: Optional[ServerInfo]
    _session_config: Optional[SessionConfig]
    _metadata: Optional[list[dict[int, Metadata]]]
    _session_is_started: bool
    _recorder: Optional[Recorder]
    _tick_unwrapper: TickUnwrapper

    def __init__(self, link: BufferedLink, protocol: Type[CommunicationProtocol]) -> None:
        self._link = link
        self._protocol = protocol
        self._server_info = None
        self._session_config = None
        self._session_is_started = False
        self._metadata = None
        self._recorder = None
        self._tick_unwrapper = TickUnwrapper()

    def _assert_connected(self):
        if not self.connected:
            raise ClientError("Client is not connected.")

    def _assert_session_setup(self):
        self._assert_connected()
        if not self.session_is_setup:
            raise ClientError("Session is not set up.")

    def _assert_session_started(self):
        self._assert_session_setup()
        if not self.session_is_started:
            raise ClientError("Session is not started.")

    def connect(self) -> None:
        """Connects to the specified host.

        :raises: Exception if the host cannot be connected to.
        """
        self._default_link_timeout = self._link.timeout
        self._link_timeout = self._default_link_timeout
        self._link.connect()

        self._link.send(self._protocol.get_sensor_info_command())
        sens_response = self._link.recv_until(self._protocol.end_sequence)
        sensor_infos = self._protocol.get_sensor_info_response(sens_response)

        self._link.send(self._protocol.get_system_info_command())
        sys_response = self._link.recv_until(self._protocol.end_sequence)
        self._server_info, sensor = self._protocol.get_system_info_response(
            sys_response, sensor_infos
        )

        if sensor != "a121":
            self._link.disconnect()
            raise ClientError(f"Wrong sensor version, expected a121 but got {sensor}")

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        """Sets up the session specified by ``config``.

        If the Client is not already connected, it will connect before setting up the session.

        :param config: The session to set up.
        :raises:
            ``ValueError`` if the config is invalid.

        :returns:
            ``Metadata`` if ``config.extended is False``,
            ``list[dict[int, Metadata]]`` otherwise.
        """
        if not self.connected:
            self.connect()

        if self.session_is_started:
            raise ClientError("Session is currently running, can't setup.")

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        config.validate()

        pc = _PerformanceCalc(config, None)

        try:
            # Increase timeout if update rate is very low, otherwise keep default
            self._link_timeout = max(1.1 * (1 / pc.frame_rate) + 0.5, self._link.timeout)
        except Exception:
            self._link_timeout = self._default_link_timeout

        self._link.timeout = self._link_timeout

        self._link.send(self._protocol.setup_command(config))
        reponse_bytes = self._link.recv_until(self._protocol.end_sequence)
        self._session_config = config
        self._metadata = self._protocol.setup_response(
            reponse_bytes, context_session_config=config
        )

        if self.session_config.extended:
            return self._metadata
        else:
            return unextend(self._metadata)

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        """Starts the already set up session.

        After this call, the server starts streaming data to the client.

        :param recorder:
            An optional ``Recorder``, which samples every ``get_next()``
        :raises: ``ClientError`` if ``Client``'s  session is not set up.
        """
        self._assert_session_setup()

        if self.session_is_started:
            raise ClientError("Session is already started.")

        if recorder is not None:
            self._recorder = recorder
            self._recorder._start(
                client_info=self.client_info,
                extended_metadata=self.extended_metadata,
                server_info=self.server_info,
                session_config=self.session_config,
            )

        self._link.timeout = self._link_timeout

        self._link.send(self._protocol.start_streaming_command())
        reponse_bytes = self._link.recv_until(self._protocol.end_sequence)
        self._protocol.start_streaming_response(reponse_bytes)
        self._session_is_started = True

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        """Gets results from the server.

        :returns:
            A ``Result`` if the setup ``SessionConfig.extended is False``,
            ``list[dict[int, Result]]`` otherwise.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        self._assert_session_started()

        payload_size, partial_results = self._protocol.get_next_header(
            bytes_=self._link.recv_until(self._protocol.end_sequence),
            extended_metadata=self.extended_metadata,
            ticks_per_second=self.server_info.ticks_per_second,
        )
        payload = self._link.recv(payload_size)
        extended_results = self._protocol.get_next_payload(payload, partial_results)

        extended_results = self._tick_unwrapper.unwrap_ticks(extended_results)

        if self._recorder is not None:
            self._recorder._sample(extended_results)

        if self.session_config.extended:
            return extended_results
        else:
            return unextend(extended_results)

    def stop_session(self) -> Any:
        """Stops an on-going session

        :returns:
            The return value of the passed ``Recorder.stop()`` passed in ``start_session``.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        self._assert_session_started()

        recorder_result = None
        if self._recorder is not None:
            recorder_result = self._recorder._stop()
            self._recorder = None

        try:
            self._link.send(self._protocol.stop_streaming_command())
            reponse_bytes = self._drain_buffer(self._link.timeout + 1)
            self._protocol.stop_streaming_response(reponse_bytes)
        except Exception:
            raise
        finally:
            self._link.timeout = self._default_link_timeout
            self._session_is_started = False
            self._tick_unwrapper = TickUnwrapper()

        return recorder_result

    def _drain_buffer(
        self, timeout_s: float = 3.0
    ) -> bytes:  # TODO: Make `timeout_s` session-dependant
        """Drains data in the buffer. Returning the first bytes that are not data packets."""
        start = time.time()

        while time.time() < start + timeout_s:
            next_header = self._link.recv_until(self._protocol.end_sequence)
            try:
                payload_size, _ = self._protocol.get_next_header(
                    bytes_=next_header,
                    extended_metadata=self.extended_metadata,
                    ticks_per_second=self.server_info.ticks_per_second,
                )
                _ = self._link.recv(payload_size)
            except Exception:
                return next_header
            else:
                log.debug("Threw away get_next package when draining buffer")
        raise ClientError("Client timed out when waiting for 'stop'-response.")

    def disconnect(self) -> None:
        """Disconnects the client from the host.

        :raises: ``ClientError`` if ``Client`` is not connected.
        """
        # TODO: Make sure this cleans up corner-cases (like lost connection)
        #       to not hog resources.
        self._assert_connected()

        if self.session_is_started:
            _ = self.stop_session()

        self._server_info = None
        self._link.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, type_, value, traceback):
        self.disconnect()

    @property
    def connected(self) -> bool:
        """Whether this Client is connected."""
        return self._server_info is not None

    @property
    def session_is_setup(self) -> bool:
        """Whether this Client has a session set up."""
        return self._session_config is not None

    @property
    def session_is_started(self) -> bool:
        """Whether this Client's session is started."""
        return self._session_is_started

    @property
    def server_info(self) -> ServerInfo:
        """The ``ServerInfo``."""
        self._assert_connected()

        return self._server_info  # type: ignore[return-value]

    @property
    def client_info(self) -> ClientInfo:
        """The ``ClientInfo``."""
        return ClientInfo()

    @property
    def session_config(self) -> SessionConfig:
        """The :class:`SessionConfig` for the current session"""

        self._assert_session_setup()
        assert self._session_config is not None  # Should never happen if session is setup
        return self._session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        """The extended :class:`Metadata` for the current session"""

        self._assert_session_setup()
        assert self._metadata is not None  # Should never happen if session is setup
        return self._metadata


class TickUnwrapper:
    """Wraps unwrap_ticks to be applied over extended results"""

    def __init__(self) -> None:
        self.next_minimum_tick: Optional[int] = None

    def unwrap_ticks(self, extended_results: list[dict[int, Result]]) -> list[dict[int, Result]]:
        result_items = list(iterate_extended_structure(extended_results))
        ticks = [result.tick for _, _, result in result_items]
        unwrapped_ticks, self.next_minimum_tick = unwrap_ticks(ticks, self.next_minimum_tick)

        def f(result_item: Tuple[int, int, Result], updated_tick: int) -> Tuple[int, int, Result]:
            group_index, sensor_id, result = result_item
            updated_result = attrs.evolve(result, tick=updated_tick)
            return (group_index, sensor_id, updated_result)

        return create_extended_structure(map(f, result_items, unwrapped_ticks))
