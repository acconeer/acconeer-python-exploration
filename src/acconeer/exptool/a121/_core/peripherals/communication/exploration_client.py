# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import contextlib
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
    ServerInfo,
    ServerLogMessage,
    SessionConfig,
)
from acconeer.exptool.a121._core.utils import (
    create_extended_structure,
    iterate_extended_structure,
    unextend,
    unwrap_ticks,
)
from acconeer.exptool.a121._perf_calc import _SessionPerformanceCalc

from .client import Client, ClientCreationError, ClientError
from .common_client import CommonClient
from .communication_protocol import CommunicationProtocol
from .exploration_protocol import (
    ExplorationProtocol,
    ServerError,
    get_exploration_protocol,
    messages,
)
from .links import AdaptedSerialLink, BufferedLink, NullLinkError
from .message import Message, MessageT
from .utils import autodetermine_client_link, get_calibrations_provided, link_factory


log = logging.getLogger(__name__)


@Client._register
class ExplorationClient(CommonClient):
    _link: BufferedLink
    _default_link_timeout: float
    _link_timeout: float
    _protocol: Type[CommunicationProtocol]
    _protocol_overridden: bool
    _tick_unwrapper: TickUnwrapper
    _server_info: Optional[ServerInfo]
    _result_queue: list[list[dict[int, Result]]]
    _message_stream: Iterator[Message]
    _log_queue: list[ServerLogMessage]

    @classmethod
    def open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ) -> Client:
        if mock is not None:
            raise ClientCreationError

        client_info = ClientInfo._from_open(
            ip_address=ip_address,
            tcp_port=tcp_port,
            override_baudrate=override_baudrate,
            serial_port=serial_port,
            usb_device=usb_device,
        )

        return cls(client_info=client_info, _override_protocol=_override_protocol)

    def __init__(
        self,
        client_info: ClientInfo = ClientInfo(mock=None),
        _override_protocol: Optional[Type[CommunicationProtocol]] = None,
    ) -> None:
        super().__init__(client_info)
        self._tick_unwrapper = TickUnwrapper()
        self._message_stream = iter([])
        self._server_info = None
        self._log_queue = []
        self._closed = False
        self._crashing = False

        self._protocol: Type[CommunicationProtocol] = ExplorationProtocol
        self._protocol_overridden = False

        if _override_protocol is not None:
            self._protocol = _override_protocol
            self._protocol_overridden = True

        self._link = link_factory(self.client_info)
        try:
            self._connect_link()
        except NullLinkError:
            self._client_info = autodetermine_client_link(self.client_info)
            self._link = link_factory(self.client_info)
            self._connect_link()

        self._connect_client()

    def _connect_link(self) -> None:
        self._default_link_timeout = self._link.timeout
        self._link_timeout = self._default_link_timeout

        try:
            self._link.connect()
        except SerialException as exc:
            if "Permission denied" in str(exc):
                text = "\n".join(
                    [
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

    def _connect_client(self) -> None:
        self._message_stream = self._get_message_stream()
        self._server_info = self._retrieve_server_info()

        if self._server_info.connected_sensors == []:
            self._link.disconnect()
            raise ClientError("Exploration server is running but no sensors are detected.")

        if not self._protocol_overridden:
            self._update_protocol_based_on_servers_rss_version()

        self._update_baudrate()

    def _get_message_stream(self) -> Iterator[Message]:
        """returns an iterator of parsed messages"""
        while True:
            with self._close_before_reraise():
                header: dict[str, Any] = json.loads(
                    self._link.recv_until(self._protocol.end_sequence)
                )

            try:
                payload_size = header["payload_size"]
            except KeyError:
                payload = bytes()
            else:
                with self._close_before_reraise():
                    payload = self._link.recv(payload_size)

            resp = self._protocol.parse_message(header, payload)
            yield resp

    @contextlib.contextmanager
    def _close_before_reraise(self) -> Iterator[None]:
        try:
            yield
        except Exception:
            self._crashing = True
            self.close()
            raise

    def _retrieve_server_info(self) -> ServerInfo:
        system_info_response = self._send_command_and_wait_for_response(
            self._protocol.get_system_info_command(),
            messages.SystemInfoResponse,
        )

        sensor = system_info_response.system_info.get("sensor")
        if sensor != "a121":
            self.close()
            raise ClientError(f"Wrong sensor version, expected a121 but got {sensor}")

        sensor_info_response = self._send_command_and_wait_for_response(
            self._protocol.get_sensor_info_command(),
            messages.SensorInfoResponse,
        )

        return ServerInfo(
            rss_version=system_info_response.system_info["rss_version"],
            sensor_count=system_info_response.system_info["sensor_count"],
            ticks_per_second=system_info_response.system_info["ticks_per_second"],
            hardware_name=system_info_response.system_info.get("hw", None),
            sensor_infos=sensor_info_response.sensor_infos,
            max_baudrate=system_info_response.system_info.get("max_baudrate"),
        )

    def _update_protocol_based_on_servers_rss_version(self) -> None:
        with self._close_before_reraise():
            self._protocol = get_exploration_protocol(self.server_info.parsed_rss_version)

    def _update_baudrate(self) -> None:
        # Only Change baudrate for AdaptedSerialLink
        if not isinstance(self._link, AdaptedSerialLink):
            return

        if self.client_info.serial is None:
            return

        DEFAULT_BAUDRATE = 115200
        overridden_baudrate = self.client_info.serial.override_baudrate
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

        _ = self._send_command_and_wait_for_response(
            self._protocol.set_baudrate_command(baudrate_to_use), messages.SetBaudrateResponse
        )
        self._link.baudrate = baudrate_to_use

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if self.session_is_started:
            raise ClientError("Session is currently running, can't setup.")

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        config.validate()

        self._calibrations_provided = get_calibrations_provided(config, calibrations)

        message = self._send_command_and_wait_for_response(
            self._protocol.setup_command(config, calibrations),
            messages.SetupResponse,
        )
        self._session_config = config
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

    def _send_command_and_wait_for_response(
        self, command: bytes, response_type: Type[MessageT], timeout_s: Optional[float] = None
    ) -> MessageT:
        with self._close_before_reraise():
            self._link.send(command)

        return self._wait_for_response(response_type, timeout_s)

    def _wait_for_response(
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

            if deadline is not None and time.monotonic() > deadline:
                raise ClientError("Client timed out.")

        raise ClientError("No message received")

    def start_session(self) -> None:
        self._assert_session_setup()

        if self.session_is_started:
            raise ClientError("Session is already started.")

        self._link.timeout = self._link_timeout
        _ = self._send_command_and_wait_for_response(
            self._protocol.start_streaming_command(),
            messages.StartStreamingResponse,
        )

        self._recorder_start_session()
        self._session_is_started = True

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        self._assert_session_started()

        result_message = self._wait_for_response(messages.ResultMessage)

        if self._metadata is None:
            raise RuntimeError(f"{self} has no metadata")

        if self._server_info is None:
            raise RuntimeError(f"{self} has no system info")

        if self._session_config is None:
            raise RuntimeError(f"{self} has no session config")

        extended_results = result_message.get_extended_results(
            tps=self._server_info.ticks_per_second,
            metadata=self._metadata,
            config_groups=self._session_config.groups,
        )

        extended_results = self._tick_unwrapper.unwrap_ticks(extended_results)

        self._recorder_sample(extended_results)
        return self._return_results(extended_results)

    def stop_session(self) -> None:
        self._assert_session_started()

        _ = self._send_command_and_wait_for_response(
            self._protocol.stop_streaming_command(),
            messages.StopStreamingResponse,
            timeout_s=self._link.timeout + 1,
        )

        self._link.timeout = self._default_link_timeout
        self._session_is_started = False
        self._recorder_stop_session()
        self._log_queue.clear()

    def close(self) -> None:
        if self._closed:
            return

        try:
            if self.session_is_started:
                if self._crashing:
                    self._session_is_started = False
                    self._recorder_stop_session()
                else:
                    self.stop_session()
        except Exception:
            raise
        finally:
            self._tick_unwrapper = TickUnwrapper()
            self._server_info = None
            self._message_stream = iter([])
            self._metadata = None
            self._log_queue.clear()
            self._link.disconnect()
            self._closed = True

    @property
    def connected(self) -> bool:
        return self._server_info is not None

    @property
    def server_info(self) -> ServerInfo:
        self._assert_connected()

        assert self._server_info is not None  # Should never happend if client is connected
        return self._server_info


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
