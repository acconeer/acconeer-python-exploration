from __future__ import annotations

from typing import Any, Optional, Union

from acconeer.exptool.a121._core.entities import (
    ClientInfo,
    Metadata,
    Result,
    SensorConfig,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core.utils import unextend

from .communication_protocol import CommunicationProtocol
from .link import BufferedLink
from .recorder import Recorder


class ClientError(Exception):
    pass


class AgnosticClient:
    _link: BufferedLink
    _protocol: CommunicationProtocol
    _server_info: Optional[ServerInfo]
    _session_config: Optional[SessionConfig]
    _metadata: Optional[list[dict[int, Metadata]]]
    _session_is_started: bool
    _recorder: Optional[Recorder]

    def __init__(self, link: BufferedLink, protocol: CommunicationProtocol) -> None:
        self._link = link
        self._protocol = protocol
        self._server_info = None
        self._session_config = None
        self._session_is_started = False
        self._metadata = None
        self._recorder = None

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
        self._link.connect()

        self._link.send(self._protocol.get_system_info_command())
        sys_response = self._link.recv_until(self._protocol.end_sequence)
        self._server_info = self._protocol.get_system_info_response(sys_response)

        self._link.send(self._protocol.get_sensor_info_command())
        sens_response = self._link.recv_until(self._protocol.end_sequence)
        _ = self._protocol.get_sensor_info_response(sens_response)

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        self._assert_connected()

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

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
        self._assert_session_setup()

        if recorder is not None:
            self._recorder = recorder
            self._recorder.start(
                client_info=self.client_info,
                extended_metadata=self.extended_metadata,
                server_info=self.server_info,
                session_config=self.session_config,
            )

        self._link.send(self._protocol.start_streaming_command())
        reponse_bytes = self._link.recv_until(self._protocol.end_sequence)
        self._session_is_started = self._protocol.start_streaming_response(reponse_bytes)

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        self._assert_session_started()

        payload_size, partial_results = self._protocol.get_next_header(
            bytes_=self._link.recv_until(self._protocol.end_sequence),
            extended_metadata=self.extended_metadata,
            ticks_per_second=self.server_info.ticks_per_second,
        )
        payload = self._link.recv(payload_size)
        extended_results = self._protocol.get_next_payload(payload, partial_results)

        if self._recorder is not None:
            self._recorder.sample(extended_results)

        if self.session_config.extended:
            return extended_results
        else:
            return unextend(extended_results)

    def stop_session(self) -> Any:
        self._assert_session_started()

        if self._recorder is not None:
            return self._recorder.stop()

        self._link.send(self._protocol.stop_streaming_command())
        reponse_bytes = self._link.recv_until(self._protocol.end_sequence)
        self._session_is_started = not self._protocol.stop_streaming_response(reponse_bytes)

    def disconnect(self) -> None:
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
        return self._server_info is not None

    @property
    def session_is_setup(self) -> bool:
        return self._session_config is not None

    @property
    def session_is_started(self) -> bool:
        return self._session_is_started

    @property
    def server_info(self) -> ServerInfo:
        self._assert_connected()

        return self._server_info  # type: ignore[return-value]

    @property
    def client_info(self) -> ClientInfo:
        return ClientInfo()

    @property
    def session_config(self) -> SessionConfig:
        self._assert_session_setup()

        return self._session_config  # type: ignore[return-value]

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        self._assert_session_setup()

        return self._metadata  # type: ignore[return-value]
