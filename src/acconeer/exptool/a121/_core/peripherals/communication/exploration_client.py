# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator, Optional, Tuple, Type, Union

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
    ServerLogMessage,
    SessionConfig,
)
from acconeer.exptool.a121._core.mediators import ClientError, Recorder
from acconeer.exptool.a121._core.utils import (
    create_extended_structure,
    iterate_extended_structure,
    unextend,
    unwrap_ticks,
)
from acconeer.exptool.a121._perf_calc import _SessionPerformanceCalc

from .common_client import CommonClient
from .communication_protocol import CommunicationProtocol
from .exploration_protocol import (
    ExplorationProtocol,
    ServerError,
    get_exploration_protocol,
    messages,
)
from .exploration_protocol.messages.system_info_response import SystemInfoDict
from .links import AdaptedSerialLink, BufferedLink, NullLinkError
from .message import Message, MessageT
from .utils import autodetermine_client_link, get_calibrations_provided, link_factory


log = logging.getLogger(__name__)


class ExplorationClient(CommonClient):
    _link: BufferedLink
    _default_link_timeout: float
    _link_timeout: float
    _protocol: Type[CommunicationProtocol]
    _protocol_overridden: bool
    _tick_unwrapper: TickUnwrapper
    _sensor_infos: dict[int, SensorInfo]
    _system_info: Optional[SystemInfoDict]
    _result_queue: list[list[dict[int, Result]]]
    _message_stream: Iterator[Message]
    _log_queue: list[ServerLogMessage]

    def __init__(
        self,
        client_info: ClientInfo,
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ) -> None:
        super().__init__(client_info)
        self._link = link_factory(self.client_info)
        self._tick_unwrapper = TickUnwrapper()
        self._message_stream = iter([])
        self._sensor_infos = {}
        self._system_info = None
        self._log_queue = []

        self._protocol: Type[CommunicationProtocol] = ExplorationProtocol
        self._protocol_overridden = False

        if _override_protocol is not None:
            self._protocol = _override_protocol
            self._protocol_overridden = True

    def _assert_connected(self) -> None:
        if not self.connected:
            raise ClientError("Client is not connected.")

    def _assert_session_setup(self) -> None:
        self._assert_connected()
        if not self.session_is_setup:
            raise ClientError("Session is not set up.")

    def _assert_session_started(self) -> None:
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
        if deadline is not None and time.monotonic() > deadline:
            raise ClientError("Client timed out.")

    def _apply_messages_until_message_type_encountered(
        self, message_type: Type[MessageT], timeout_s: Optional[float] = None
    ) -> MessageT:
        """Retrieves and applies messages until a message of type ``message_type`` is encountered.

        :param message_type: a subclass of ``Message``
        :param timeout_s: Limit the time spent in this function
        :raises ClientError:
            if timeout_s is set and that amount of time has elapsed
            without predicate evaluating to True
        """
        deadline = None if (timeout_s is None) else time.monotonic() + timeout_s

        if message_type in [messages.ErroneousMessage, messages.EmptyResultMessage]:
            raise ClientError("Cannot wait for error messages")

        for message in self._message_stream:
            if type(message) == messages.LogMessage:
                self._log_queue.append(message.message)
            elif type(message) == messages.EmptyResultMessage:
                raise RuntimeError("Received an empty Result from Server.")
            elif type(message) == messages.ErroneousMessage:
                last_error = ""
                for log in self._log_queue:
                    if log.level == "ERROR" and "exploration_server" not in log.module:
                        last_error = f" ({log.log})"
                raise ServerError(f"{message}{last_error}")

            if type(message) == message_type:
                return message

            self._assert_deadline_not_reached(deadline)
        raise ClientError("No message received")

    def _connect_link(self) -> None:
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
        system_info_response = self._apply_messages_until_message_type_encountered(
            messages.SystemInfoResponse
        )
        self._system_info = system_info_response.system_info

        self._link.send(self._protocol.get_sensor_info_command())
        sensor_info_response = self._apply_messages_until_message_type_encountered(
            messages.SensorInfoResponse
        )
        self._sensor_infos = sensor_info_response.sensor_infos

        sensor = self._system_info.get("sensor") if self._system_info else None
        if sensor != "a121":
            self._link.disconnect()
            raise ClientError(f"Wrong sensor version, expected a121 but got {sensor}")

        if not self._protocol_overridden:
            self._update_protocol_based_on_servers_rss_version()

        self._update_baudrate()

    def _update_protocol_based_on_servers_rss_version(self) -> None:
        try:
            new_protocol = get_exploration_protocol(self.server_info.parsed_rss_version)
        except Exception:
            self.disconnect()
            raise
        else:
            self._protocol = new_protocol

    def _update_baudrate(self) -> None:
        # Only Change baudrate for AdaptedSerialLink
        if not isinstance(self._link, AdaptedSerialLink):
            return

        DEFAULT_BAUDRATE = 115200
        overridden_baudrate = self.client_info.override_baudrate
        max_baudrate = self.server_info.max_baudrate
        baudrate_to_use = self.server_info.max_baudrate or DEFAULT_BAUDRATE

        # Override baudrate?
        if overridden_baudrate is not None and max_baudrate is not None:
            # Valid Baudrate?
            if overridden_baudrate > max_baudrate:
                raise ClientError(f"Cannot set a baudrate higher than {max_baudrate}")
            elif overridden_baudrate < DEFAULT_BAUDRATE:
                raise ClientError(f"Cannot set a baudrate lower than {DEFAULT_BAUDRATE}")
            baudrate_to_use = overridden_baudrate

        # Do not change baudrate if DEFAULT_BAUDRATE
        if baudrate_to_use == DEFAULT_BAUDRATE:
            return

        self._link.send(self._protocol.set_baudrate_command(baudrate_to_use))

        self._apply_messages_until_message_type_encountered(messages.SetBaudrateResponse)
        self._baudrate_ack_received = False

        self._link.baudrate = baudrate_to_use

    def connect(self) -> None:
        try:
            self._connect_link()
        except NullLinkError:
            self._client_info = autodetermine_client_link(self.client_info)
            self._link = link_factory(self.client_info)
            self._connect_link()

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if not self.connected:
            self.connect()

        if self.session_is_started:
            raise ClientError("Session is currently running, can't setup.")

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        config.validate()

        self._calibrations_provided = get_calibrations_provided(config, calibrations)

        self._link.send(self._protocol.setup_command(config, calibrations))

        self._session_config = config

        message = self._apply_messages_until_message_type_encountered(messages.SetupResponse)
        self._metadata = [
            {
                sensor_id: metadata
                for metadata, sensor_id in zip(metadata_group, config_group.keys())
            }
            for metadata_group, config_group in zip(
                message.grouped_metadatas, self._session_config.groups
            )
        ]
        self._sensor_calibrations = message.sensor_calibrations
        pc = _SessionPerformanceCalc(config, self._metadata)

        try:
            # Use max of the calculate duration and update/frame rate to guarantee sufficient
            # timeout.
            timeout_duration = max(pc.update_duration, 1 / pc.update_rate)
            # Increase timeout if update rate is very low, otherwise keep default
            self._link_timeout = max(1.5 * timeout_duration + 1.0, self._default_link_timeout)
        except Exception:
            self._link_timeout = self._default_link_timeout

        self._link.timeout = self._link_timeout

        if self.session_config.extended:
            return self._metadata
        else:
            return unextend(self._metadata)

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        self._assert_session_setup()

        if self.session_is_started:
            raise ClientError("Session is already started.")

        self._recorder_start(recorder)
        self._create_rate_stats_calc()
        self._session_is_started = True

        self._link.timeout = self._link_timeout
        self._link.send(self._protocol.start_streaming_command())
        self._apply_messages_until_message_type_encountered(messages.StartStreamingResponse)

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        self._assert_session_started()

        result_message = self._apply_messages_until_message_type_encountered(
            messages.ResultMessage
        )

        if self._metadata is None:
            raise RuntimeError(f"{self} has no metadata")

        if self._system_info is None:
            raise RuntimeError(f"{self} has no system info")

        if self._session_config is None:
            raise RuntimeError(f"{self} has no session config")

        extended_results = result_message.get_extended_results(
            tps=self._system_info["ticks_per_second"],
            metadata=self._metadata,
            config_groups=self._session_config.groups,
        )

        self._recorder_sample(extended_results)
        self._update_rate_stats_calc(extended_results)
        return self._return_results(extended_results)

    def stop_session(self) -> Any:
        self._assert_session_started()

        self._link.send(self._protocol.stop_streaming_command())

        try:
            self._apply_messages_until_message_type_encountered(
                messages.StopStreamingResponse, timeout_s=self._link.timeout + 1
            )
            self._session_is_started = False
        except Exception:
            raise
        finally:
            self._link.timeout = self._default_link_timeout
            self._tick_unwrapper = TickUnwrapper()

        recorder_result = self._recorder_stop()
        self._rate_stats_calc = None
        self._log_queue.clear()

        return recorder_result

    def disconnect(self) -> None:
        # TODO: Make sure this cleans up corner-cases (like lost connection)
        #       to not hog resources.

        if self.session_is_started:
            _ = self.stop_session()

        self._system_info = None
        self._sensor_infos = {}
        self._message_stream = iter([])
        self._metadata = None
        self._log_queue.clear()
        self._link.disconnect()

    @property
    def connected(self) -> bool:
        return self._sensor_infos != {} and self._system_info is not None

    @property
    def server_info(self) -> ServerInfo:
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
