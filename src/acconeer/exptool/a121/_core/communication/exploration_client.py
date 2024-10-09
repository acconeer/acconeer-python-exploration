# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import logging
from typing import NoReturn, Optional, Tuple, Type, TypeVar, Union

import attrs
import typing_extensions as te

from acconeer.exptool._core.communication import (
    BufferedLink,
    ClientCreationError,
    ClientError,
    ExploreSerialLink,
    Message,
    MessageStream,
)
from acconeer.exptool._core.communication.client import ServerError
from acconeer.exptool._core.communication.communication_protocol import messages
from acconeer.exptool._core.communication.communication_protocol.messages.log_message import (
    ServerLog,
)
from acconeer.exptool._core.communication.links.helpers import ensure_connected_link
from acconeer.exptool._core.communication.unwrap_ticks import unwrap_ticks
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a121._core.entities import (
    Metadata,
    Result,
    SensorCalibration,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.utils import (
    create_extended_structure,
    iterate_extended_structure,
    unextend,
)
from acconeer.exptool.a121._perf_calc import _SessionPerformanceCalc

from .client import Client
from .exploration_protocol import (
    ExplorationProtocol,
    get_exploration_protocol,
)
from .exploration_protocol import (
    messages as a121_messages,
)
from .utils import get_calibrations_provided


_MessageT = TypeVar("_MessageT", bound=Message)
log = logging.getLogger(__name__)


class ExplorationClient(Client, register=True):
    _link: BufferedLink
    _protocol: Type[ExplorationProtocol]
    _tick_unwrapper: TickUnwrapper
    _server_info: Optional[ServerInfo]
    _result_queue: list[list[dict[int, Result]]]
    _log_queue: list[ServerLog]

    @classmethod
    def open(
        cls,
        ip_address: Optional[str] = None,
        tcp_port: Optional[int] = None,
        serial_port: Optional[str] = None,
        usb_device: Optional[Union[str, bool]] = None,
        mock: Optional[bool] = None,
        override_baudrate: Optional[int] = None,
        flow_control: bool = True,
        generation: Optional[str] = "a121",
    ) -> te.Self:
        if generation != "a121":
            raise ClientCreationError

        if mock is not None:
            raise ClientCreationError

        client_info = ClientInfo._from_open(
            ip_address=ip_address,
            tcp_port=tcp_port,
            override_baudrate=override_baudrate,
            serial_port=serial_port,
            usb_device=usb_device,
            flow_control=flow_control,
        )

        return cls(client_info=client_info)

    def __init__(
        self,
        client_info: ClientInfo = ClientInfo(mock=None),
        _override_protocol: Optional[Type[ExplorationProtocol]] = None,
    ) -> None:
        super().__init__(client_info)
        self._tick_unwrapper = TickUnwrapper()
        self._server_info = None
        self._log_queue = []
        self._closed = False
        self._crashing = False

        self._protocol = ExplorationProtocol

        (self._link, self._client_info) = ensure_connected_link(self.client_info)
        self._server_stream = MessageStream(
            self._link,
            self._protocol,
            message_handler=self._handle_messages,
            link_error_callback=self._close_before_reraise,
        )

        self._server_info = self._retrieve_server_info()

        if self._server_info.connected_sensors == []:
            self._link.disconnect()
            msg = "Exploration server is running but no sensors are detected."
            raise ClientError(msg)

        if _override_protocol is None:
            most_suitable_protocol = get_exploration_protocol(self.server_info.parsed_rss_version)

            self._server_stream.protocol = most_suitable_protocol
            self._protocol = most_suitable_protocol
        else:
            self._server_stream.protocol = _override_protocol
            self._protocol = _override_protocol

        self._update_baudrate()

    def _close_before_reraise(self, exception: Exception) -> NoReturn:
        self._crashing = True
        self.close()
        raise exception

    def _retrieve_server_info(self) -> ServerInfo:
        self._server_stream.send_command(self._protocol.get_system_info_command())
        system_info_response = self._server_stream.wait_for_message(messages.SystemInfoResponse)

        sensor = system_info_response.system_info.get("sensor")
        if sensor != "a121":
            self.close()
            msg = f"Wrong sensor version, expected a121 but got {sensor}"
            raise ClientError(msg)

        self._server_stream.send_command(self._protocol.get_sensor_info_command())
        sensor_info_response = self._server_stream.wait_for_message(
            a121_messages.SensorInfoResponse
        )

        return ServerInfo(
            rss_version=system_info_response.system_info["rss_version"],
            sensor_count=system_info_response.system_info["sensor_count"],
            ticks_per_second=system_info_response.system_info["ticks_per_second"],
            hardware_name=system_info_response.system_info.get("hw", None),
            sensor_infos=sensor_info_response.sensor_infos,
            max_baudrate=system_info_response.system_info.get("max_baudrate"),
        )

    def _update_baudrate(self) -> None:
        # Only Change baudrate for ExploreSerialLink
        if not isinstance(self._link, ExploreSerialLink):
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
                msg = f"Cannot set a baudrate higher than {max_baudrate}"
                raise ClientError(msg)
            elif overridden_baudrate < DEFAULT_BAUDRATE:
                msg = f"Cannot set a baudrate lower than {DEFAULT_BAUDRATE}"
                raise ClientError(msg)
            baudrate_to_use = overridden_baudrate

        # Do not change baudrate if DEFAULT_BAUDRATE
        if baudrate_to_use == DEFAULT_BAUDRATE:
            return

        self._server_stream.send_command(self._protocol.set_baudrate_command(baudrate_to_use))
        _ = self._server_stream.wait_for_message(messages.SetBaudrateResponse)

        self._link.baudrate = baudrate_to_use

    def setup_session(  # type: ignore[override]
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if self.session_is_started:
            msg = "Session is currently running, can't setup."
            raise ClientError(msg)

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        config.validate()

        self._calibrations_provided = get_calibrations_provided(config, calibrations)
        self._session_config = config

        self._server_stream.send_command(self._protocol.setup_command(config, calibrations))
        setup_response = self._server_stream.wait_for_message(a121_messages.SetupResponse)

        self._metadata = [
            {
                sensor_id: metadata
                for metadata, sensor_id in zip(metadata_group, config_group.keys())
            }
            for metadata_group, config_group in zip(
                setup_response.grouped_metadatas, self._session_config.groups
            )
        ]
        self._sensor_calibrations = setup_response.sensor_calibrations

        if self.session_config.extended:
            return self._metadata
        else:
            return unextend(self._metadata)

    def _handle_messages(self, message: Message) -> None:
        if type(message) is messages.LogMessage:
            self._log_queue.append(message.message)
        elif type(message) is a121_messages.EmptyResultMessage:
            msg = "Received an empty Result from Server."
            raise RuntimeError(msg)
        elif type(message) is messages.ErroneousMessage:
            last_error = ""
            for log in self._log_queue:
                if log.level == "ERROR" and "exploration_server" not in log.module:
                    last_error = f" ({log.log})"
            msg = f"{message}{last_error}"
            raise ServerError(msg)

    def start_session(self) -> None:
        self._assert_session_setup()

        if self.session_is_started:
            msg = "Session is already started."
            raise ClientError(msg)

        assert self._session_config is not None

        pc = _SessionPerformanceCalc(self._session_config, self._metadata)

        try:
            # Use max of the calculate duration and update/frame rate to guarantee sufficient
            # timeout.
            timeout_duration = max(pc.update_duration, 1 / pc.update_rate)
            # Increase timeout if update rate is very low, otherwise keep default
            timeout = max(1.5 * timeout_duration + 1.0, self._link.DEFAULT_TIMEOUT)
        except Exception:
            timeout = self._link.DEFAULT_TIMEOUT

        self._link.timeout = timeout

        self._server_stream.send_command(self._protocol.start_streaming_command())
        _ = self._server_stream.wait_for_message(messages.StartStreamingResponse)

        self._recorder_start_session()
        self._session_is_started = True

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:  # type: ignore[override]
        self._assert_session_started()

        result_message = self._server_stream.wait_for_message(a121_messages.ResultMessage)

        if self._metadata is None:
            msg = f"{self} has no metadata"
            raise RuntimeError(msg)

        if self._server_info is None:
            msg = f"{self} has no system info"
            raise RuntimeError(msg)

        if self._session_config is None:
            msg = f"{self} has no session config"
            raise RuntimeError(msg)

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

        self._server_stream.send_command(self._protocol.stop_streaming_command())
        _ = self._server_stream.wait_for_message(
            messages.StopStreamingResponse,
            timeout_s=self._link.timeout + 1,
        )

        self._link.timeout = self._link.DEFAULT_TIMEOUT
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
