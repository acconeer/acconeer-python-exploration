# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import attrs
import typing_extensions as te

from acconeer.exptool._core.communication import Message, MessageStream, client, messages
from acconeer.exptool._core.communication.links.helpers import ensure_connected_link
from acconeer.exptool._core.communication.unwrap_ticks import unwrap_ticks
from acconeer.exptool._core.entities import ClientInfo
from acconeer.exptool.a2._core.communication.client import Client as A2Client
from acconeer.exptool.a2._core.entities import GroupResult, Metadata, ServerInfo, SessionConfig

from .exploration_protocol import ExplorationProtocol
from .messages import ResultMessage, SetupResponse


def _naive_timeout(config: SessionConfig, minimum_timeout_s: float) -> float:
    """
    Naive assumption of measurement duration of each point,
    with a minimum timeout of ``minimum_timeout_s``
    """
    assumed_hwaas = 1
    seconds_per_point = 1e-5 + assumed_hwaas * 1e-6

    num_measurements = sum(
        sum(subsweep_config.num_points for subsweep_config in sc.subsweeps) * sc.sweeps_per_frame
        for sc in config.sensor_configs
    )

    update_period = 1 / config.update_rate if config.update_rate else 0

    config_frame_rates = [
        sensor_config.frame_rate
        for sensor_config in config.sensor_configs
        if sensor_config.frame_rate
    ]
    frame_period = 1 / min(config_frame_rates) if config_frame_rates else 0

    good_margin_factor = 1.1

    return good_margin_factor * max(
        update_period,
        frame_period,
        minimum_timeout_s,
        num_measurements * seconds_per_point,
    )


class ExplorationClient(A2Client, register=True):
    @classmethod
    def open(
        cls,
        ip_address: str | None = None,
        tcp_port: int | None = None,
        serial_port: str | None = None,
        usb_device: str | bool | None = None,
        mock: bool | None = None,
        override_baudrate: int | None = None,
        flow_control: bool = True,
        generation: str | None = "a2",
    ) -> te.Self:
        if generation not in ["a2", "a211"]:
            raise client.ClientCreationError

        if mock is not None:
            raise client.ClientCreationError

        client_info = ClientInfo._from_open(
            ip_address=ip_address,
            tcp_port=tcp_port,
            override_baudrate=override_baudrate,
            flow_control=flow_control,
            serial_port=serial_port,
            usb_device=usb_device,
        )

        return cls(client_info=client_info)

    def __init__(
        self,
        client_info: ClientInfo,
        enable_diagnostics: bool = False,
        enable_log: str = "ERROR",
    ) -> None:
        super().__init__(client_info, enable_diagnostics)

        self._enable_log = enable_log

        self._protocol = ExplorationProtocol
        self._tick_unwrapper = TickUnwrapper()
        self._log_queue: list[messages.ServerLog] = []

        (self._link, self._client_info) = ensure_connected_link(self.client_info, "a2")
        self._server_stream = MessageStream(
            self._link, self._protocol, self._handle_messages, self._close_before_reraise
        )

        self._server_stream.send_command(self._protocol.get_system_info_command())
        system_info_response = self._server_stream.wait_for_message(messages.SystemInfoResponse)

        sensor = system_info_response.system_info.get("sensor")
        if sensor not in ["a2", "a211"]:
            self.close()
            msg = f"Wrong sensor version, expected a2 or a211 but got {sensor}"
            raise client.ClientError(msg)

        self._server_info: ServerInfo | None = ServerInfo(
            rss_version=system_info_response.system_info["rss_version"],
            ticks_per_second=system_info_response.system_info["ticks_per_second"],
            hardware_name=system_info_response.system_info.get("hw"),
            sensor_serial=system_info_response.system_info.get("serial"),
            max_baudrate=system_info_response.system_info.get("max_baudrate"),
        )

    def setup_session(self, config: SessionConfig, calibration: str | None = None) -> Metadata:
        self._config = config
        self._calibration_provided = calibration is not None
        self._server_stream.send_command(
            self._protocol.setup_command(
                config,
                enable_diagnostics=self._enable_diagnostics,
                enable_log=self._enable_log,
                calibration=calibration,
            )
        )
        setup_response = self._server_stream.wait_for_message(SetupResponse)
        self._metadata = Metadata(
            tick_period=setup_response.tick_period,
            sensor_calibration=setup_response.calibration,
            update_period=setup_response.update_period,
        )
        self._sensor_calibration = setup_response.calibration
        return self._metadata

    def start_session(self) -> None:
        self._assert_session_setup()
        assert self._config is not None

        if self.session_is_started:
            msg = "Session is already started"
            raise client.ClientError(msg)

        self._server_stream.send_command(self._protocol.start_streaming_command())
        _ = self._server_stream.wait_for_message(messages.StartStreamingResponse)

        self._link.timeout = self._calculate_timeout()

        self._recorder_start_session()
        self._session_is_started = True

    def _get_next_group_result(self) -> GroupResult:
        self._assert_session_started()
        assert self._config is not None

        result_message = self._server_stream.wait_for_message(ResultMessage)
        group_result = result_message.create_result(self._config, self.server_info.rss_version)
        group_result = self._tick_unwrapper.update_ticks(group_result)

        return group_result

    def stop_session(self) -> None:
        self._server_stream.send_command(self._protocol.stop_streaming_command())
        _ = self._server_stream.wait_for_message(
            messages.StopStreamingResponse,
            timeout_s=self._link.timeout + 1,
        )

        self._link.timeout = self._link.DEFAULT_TIMEOUT
        self._session_is_started = False
        self._recorder_stop_session()
        self._log_queue.clear()

    @property
    def server_info(self) -> ServerInfo:
        self._assert_connected()
        assert self._server_info is not None

        return self._server_info

    @property
    def connected(self) -> bool:
        return self._server_info is not None

    @property
    def tick_period(self) -> int:
        self._assert_session_setup()
        assert self._metadata is not None

        return self._metadata.tick_period

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
            self._tick_unwrapper.reset()
            self._server_info = None
            self._metadata = None
            self._log_queue.clear()
            self._link.disconnect()
            self._closed = True

    def _handle_messages(self, message: Message) -> None:
        if type(message) is messages.LogMessage:
            self._log_queue.append(message.message)
        elif type(message) is messages.ErroneousMessage:
            last_error = ""
            for log in self._log_queue:
                if log.level == "ERROR" and "exploration_server" not in log.module:
                    last_error = f" ({log.log})"
            msg = f"{message}{last_error}"
            raise client.ServerError(msg)

    def _close_before_reraise(self, exception: Exception) -> te.NoReturn:
        self._crashing = True
        self.close()
        raise exception

    def _calculate_timeout(self) -> float:
        assert self._metadata is not None
        if self._metadata.update_period:
            # Add some extra margin to allow the data to be fully transferred
            timeout = self._metadata.update_period + 1.0
        else:
            assert self._config is not None
            timeout = _naive_timeout(self._config, self._link.DEFAULT_TIMEOUT)

        return timeout


@attrs.mutable
class TickUnwrapper:
    minimum_tick: int | None = None

    def update_ticks(self, group_result: GroupResult) -> GroupResult:
        (unwrapped_ticks, self.minimum_tick) = unwrap_ticks(
            [r.tick for r in group_result.results], self.minimum_tick
        )

        return attrs.evolve(
            group_result,
            results=[
                attrs.evolve(result, tick=unwrapped_tick)
                for unwrapped_tick, result in zip(unwrapped_ticks, group_result.results)
            ],
        )

    def reset(self) -> None:
        self.minimum_tick = None
