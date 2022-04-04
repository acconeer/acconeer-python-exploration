from __future__ import annotations

from typing import Any, Optional, Union

from ._client_info import ClientInfo
from ._metadata import Metadata
from ._recorder import Recorder
from ._result import Result
from ._sensor_config import SensorConfig
from ._server_info import ServerInfo
from ._session_config import SessionConfig


class Client:
    def __init__(self) -> None:
        pass

    def connect(self) -> None:
        pass

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        pass

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        pass

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        pass

    def stop_session(self) -> Any:
        pass

    def disconnect(self) -> None:
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, type_, value, traceback):
        self.disconnect()

    @property
    def connected(self) -> bool:
        pass

    @property
    def session_is_setup(self) -> bool:
        pass

    @property
    def session_is_started(self) -> bool:
        pass

    @property
    def server_info(self) -> ServerInfo:
        pass

    @property
    def client_info(self) -> ClientInfo:
        pass

    @property
    def session_config(self) -> SessionConfig:
        pass

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        pass
