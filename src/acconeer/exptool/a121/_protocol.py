from __future__ import annotations

import json
from typing import Any

from typing_extensions import Protocol

from ._session_config import SessionConfig


class CommunicationProtocol(Protocol):
    def get_system_info_command(self) -> bytes:
        ...

    def get_sensor_info_command(self) -> bytes:
        ...

    def setup_command(self, session_config: SessionConfig) -> bytes:
        ...


class ExplorationProtocol(CommunicationProtocol):
    @classmethod
    def get_system_info_command(cls) -> bytes:
        return b'{"cmd":"get_system_info"}\n'

    @classmethod
    def get_sensor_info_command(cls) -> bytes:
        return b'{"cmd":"get_sensor_info"}\n'

    @classmethod
    def setup_command(cls, session_config: SessionConfig) -> bytes:
        result = session_config.to_dict()
        # Exploration server is not interested in this.
        result.pop("extended")
        result["cmd"] = "setup"
        result["groups"] = cls._translate_groups_representation(session_config.to_dict()["groups"])
        return json.dumps(
            result,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")

    @classmethod
    def _translate_groups_representation(
        cls, groups_list: list[dict[int, Any]]
    ) -> list[list[dict[str, Any]]]:
        """
        This function translates the Exptool representation, which is

        groups = [
            {sensor_id1: config1, sensor_id2: config2, ...},  # Group 1
            ...,
        ]

        To the representation the Exploration server expects;

        groups = [
            [  # Group 1
                {"sensor_id": sensor_id1, "config": config1},
                {"sensor_id": sensor_id2, "config": config2},
                ...
            ],
            ...
        ]

        """
        return [
            [{"sensor_id": sensor_id, "config": config} for sensor_id, config in group.items()]
            for group in groups_list
        ]
