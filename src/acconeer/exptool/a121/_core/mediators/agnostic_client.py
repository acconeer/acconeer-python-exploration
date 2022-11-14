# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Iterator, Optional, Tuple, Type, Union

import attrs
from serial.serialutil import SerialException

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    SensorInfo,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.utils import (
    create_extended_structure,
    iterate_extended_structure,
    unextend,
    unwrap_ticks,
)
from acconeer.exptool.a121._perf_calc import _SessionPerformanceCalc
from acconeer.exptool.a121._rate_calc import _RateCalculator, _RateStats

from .communication_protocol import CommunicationProtocol
from .link import BufferedLink
from .message import AgnosticClientFriends, Message, SystemInfoDict
from .recorder import Recorder


log = logging.getLogger(__name__)


class ClientError(Exception):
    pass


class AgnosticClient(AgnosticClientFriends):
    _link: BufferedLink
    _default_link_timeout: float
    _link_timeout: float
    _protocol: Type[CommunicationProtocol]
    _recorder: Optional[Recorder]
    _tick_unwrapper: TickUnwrapper
    _rate_stats_calc: Optional[_RateCalculator]

    # Message friend fields
    _session_config: Optional[SessionConfig]
    _session_is_started: bool
    _metadata: Optional[list[dict[int, Metadata]]]
    _sensor_calibrations: Optional[dict[int, SensorCalibration]]
    _calibrations_provided: dict[int, bool]
    _sensor_infos: dict[int, SensorInfo]
    _system_info: Optional[SystemInfoDict]
    _result_queue: list[list[dict[int, Result]]]
    _message_stream: Iterator[Message]

    def __init__(self, link: BufferedLink, protocol: Type[CommunicationProtocol]) -> None:
        self._link = link
        self._protocol = protocol
        self._recorder = None
        self._tick_unwrapper = TickUnwrapper()
        self._message_stream = iter([])
        self._rate_stats_calc = None

        self._session_config = None
        self._session_is_started = False
        self._metadata = None
        self._sensor_calibrations = None
        self._calibrations_provided = {}
        self._sensor_infos = {}
        self._system_info = None
        self._result_queue = []

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

    def _get_message_stream(self) -> Iterator[Message]:
        """returns an iterator of parsed messages"""
        while True:
            header: dict[str, Any] = json.loads(self._link.recv_until(self._protocol.end_sequence))
            try:
                payload_size = header["payload_size"]
            except KeyError:
                payload = bytes()
            else:
                payload = self._link.recv(payload_size)

            resp = self._protocol.parse_message(header, payload)
            yield resp

    def _assert_deadline_not_reached(self, deadline: Optional[float]) -> None:
        if deadline is not None and time.time() > deadline:
            raise ClientError("Client timed out.")

    def _apply_messages_until_message_type_encountered(
        self, message_type: Type[Message], timeout_s: Optional[float] = None
    ) -> None:
        """Retrieves and applies messages until a message of type ``message_type`` is encountered.

        :param message_type: a subclass of ``Message``
        :param timeout_s: Limit the time spent in this function
        :raises ClientError:
            if timeout_s is set and that amount of time has elapsed
            without predicate evaluating to True
        """
        deadline = None if (timeout_s is None) else time.time() + timeout_s

        for message in self._message_stream:
            message.apply(self)

            if type(message) == message_type:
                return

            self._assert_deadline_not_reached(deadline)

    def _apply_messages_until(
        self, predicate: Callable[[], bool], timeout_s: Optional[float] = None
    ) -> None:
        """Retrieves and applies messages until `predicate` evaluates to True

        :param predicate: The stop condition
        :param timeout_s: Limit the time spent in this function
        :raises ClientError:
            if timeout_s is set and that amount of time has elapsed
            without predicate evaluating to True
        """
        if predicate():
            return

        deadline = None if (timeout_s is None) else time.time() + timeout_s

        for message in self._message_stream:
            # OBS! When iterating self._message_stream, each message is "consumed" from the stream.
            #      I.e. there is no way to get it back outside this loop.
            #      This means that we always should ".apply" unless
            #      we have a really good reason not to.
            message.apply(self)

            if predicate():
                return

            self._assert_deadline_not_reached(deadline)

    def connect(self) -> None:
        """Connects to the specified host.

        :raises: Exception if the host cannot be connected to.
        :raises: ClientError if server has wrong sensor generation (e.g. "a111")
        """
        self._default_link_timeout = self._link.timeout
        self._link_timeout = self._default_link_timeout

        try:
            self._link.connect()
        except SerialException as exc:
            if "Permission denied" in str(exc):
                text = "\n".join(
                    [
                        str(exc),
                        "",
                        "You are probably missing permissions to access the serial port.",
                        "",
                        "Run the setup script to fix it:",
                        "$ python -m acconeer.exptool.setup",
                        "",
                        "Reboot for the changes to take effect.",
                    ]
                )
                raise ClientError(text) from exc
            else:
                raise

        self._message_stream = self._get_message_stream()

        self._link.send(self._protocol.get_system_info_command())
        self._apply_messages_until(lambda: self._system_info is not None)

        self._link.send(self._protocol.get_sensor_info_command())
        self._apply_messages_until(lambda: self._sensor_infos != {})

        sensor = self._system_info.get("sensor") if self._system_info else None
        if sensor != "a121":
            self._link.disconnect()
            raise ClientError(f"Wrong sensor version, expected a121 but got {sensor}")

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        """Sets up the session specified by ``config``.

        If the Client is not already connected, it will connect before setting up the session.

        :param config: The session to set up.
        :param calibrations: An optional dict with :class:`SensorCalibration` for the session.
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

        self._calibrations_provided = {}
        for _, sensor_id, _ in iterate_extended_structure(config.groups):
            if calibrations:
                self._calibrations_provided[sensor_id] = sensor_id in calibrations
            else:
                self._calibrations_provided[sensor_id] = False

        self._link.send(self._protocol.setup_command(config, calibrations))

        self._session_config = config

        self._metadata = None
        self._apply_messages_until(lambda: self._metadata is not None)

        assert self._metadata is not None

        pc = _SessionPerformanceCalc(config, self._metadata)

        try:
            # Increase timeout if update rate is very low, otherwise keep default
            self._link_timeout = max(1.5 * (1 / pc.update_rate) + 1.0, self._default_link_timeout)
        except Exception:
            self._link_timeout = self._default_link_timeout

        self._link.timeout = self._link_timeout

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
            calibrations_provided: Optional[dict[int, bool]] = self.calibrations_provided
            try:
                calibrations = self.calibrations
            except ClientError:
                calibrations = None
                calibrations_provided = None

            self._recorder = recorder
            self._recorder._start(
                client_info=self.client_info,
                extended_metadata=self.extended_metadata,
                server_info=self.server_info,
                session_config=self.session_config,
                calibrations=calibrations,
                calibrations_provided=calibrations_provided,
            )

        self._link.timeout = self._link_timeout

        self._link.send(self._protocol.start_streaming_command())
        self._apply_messages_until(lambda: self.session_is_started)

        assert self._metadata is not None
        self._rate_stats_calc = _RateCalculator(self.session_config, self._metadata)

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        """Gets results from the server.

        :returns:
            A ``Result`` if the setup ``SessionConfig.extended is False``,
            ``list[dict[int, Result]]`` otherwise.
        :raises:
            ``ClientError`` if ``Client``'s session is not started.
        """
        self._assert_session_started()

        self._apply_messages_until(lambda: len(self._result_queue) > 0)
        extended_results = self._result_queue.pop(0)

        if self._recorder is not None:
            self._recorder._sample(extended_results)

        assert self._rate_stats_calc is not None
        self._rate_stats_calc.update(extended_results)

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

        self._link.send(self._protocol.stop_streaming_command())

        try:
            self._apply_messages_until(
                lambda: not self.session_is_started, timeout_s=self._link.timeout + 1
            )
        except Exception:
            raise
        finally:
            self._link.timeout = self._default_link_timeout
            self._tick_unwrapper = TickUnwrapper()
            self._result_queue = []  # results that are recv:ed post stop_session are discarded

        if self._recorder is None:
            recorder_result = None
        else:
            recorder_result = self._recorder._stop()
            self._recorder = None

        self._rate_stats_calc = None

        return recorder_result

    def disconnect(self) -> None:
        """Disconnects the client from the host."""

        # TODO: Make sure this cleans up corner-cases (like lost connection)
        #       to not hog resources.

        if self.session_is_started:
            _ = self.stop_session()

        self._system_info = None
        self._sensor_infos = {}
        self._message_stream = iter([])
        self._metadata = None
        self._link.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, type_, value, traceback):
        self.disconnect()

    @property
    def connected(self) -> bool:
        """Whether this Client is connected."""

        return self._sensor_infos != {} and self._system_info is not None

    @property
    def session_is_setup(self) -> bool:
        """Whether this Client has a session set up."""
        return self._metadata is not None

    @property
    def session_is_started(self) -> bool:
        """Whether this Client's session is started."""
        return self._session_is_started

    @property
    def server_info(self) -> ServerInfo:
        """The ``ServerInfo``."""
        self._assert_connected()

        assert self._system_info is not None  # Should never happend if client is connected
        return ServerInfo(
            rss_version=self._system_info["rss_version"],
            sensor_count=self._system_info["sensor_count"],
            ticks_per_second=self._system_info["ticks_per_second"],
            hardware_name=self._system_info.get("hw", None),
            sensor_infos=self._sensor_infos,
            max_baudrate=self._system_info.get("max_baudrate"),
        )

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

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        """
        Returns a dict with a :class:`SensorCalibration` per used
        sensor for the current session:

        For example, if session_setup was called with

        .. code-block:: python

            client.setup_session(
                SessionConfig({1: SensorConfig(), 3: SensorConfig()}),
            )

        this attribute will return {1: SensorCalibration(...), 3: SensorCalibration(...)}
        """

        self._assert_session_setup()

        if not self._sensor_calibrations:
            raise ClientError("Server did not provide calibration")

        return self._sensor_calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        """
        Returns whether a calibration was provided for each sensor in
        setup_session. For example, if setup_session was called with

        .. code-block:: python

            client.setup_session(
                SessionConfig({1: SensorConfig(), 2: SensorConfig()}),
                calibrations={2: SensorCalibration(...)},
            )

        this attribute will return ``{1: False, 2: True}``
        """

        return self._calibrations_provided

    @property
    def _rate_stats(self) -> _RateStats:
        self._assert_session_started()
        assert self._rate_stats_calc is not None
        return self._rate_stats_calc.stats


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
