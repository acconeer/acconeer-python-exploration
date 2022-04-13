from __future__ import annotations

import json
from typing import Any, Literal, Union

import numpy as np

from acconeer.exptool.a121 import Metadata, ServerInfo, SessionConfig
from acconeer.exptool.a121._entities.containers._metadata import SensorDataType

from typing_extensions import TypedDict

from .communication_protocol import CommunicationProtocol


class Response(TypedDict):
    status: str


class GetSystemInfoResponse(Response):
    rss_version: str
    sensor: str
    sensor_count: int
    ticks_per_second: int
    hw: str


class GetSensorInfoResponse(Response):
    sensor_info: list[dict[Literal["connected"], bool]]


class MetadataResponse(TypedDict):
    frame_data_length: int
    sweep_data_length: int
    subsweep_data_offset: list[int]
    subsweep_data_length: list[int]
    data_type: Union[Literal["int_16_complex"], Literal["int_16"], Literal["uint_16"]]


class SetupResponse(Response):
    tick_period: int
    metadata: list[list[MetadataResponse]]


class ExplorationProtocol(CommunicationProtocol):
    @classmethod
    def get_system_info_command(cls) -> bytes:
        return b'{"cmd":"get_system_info"}\n'

    @classmethod
    def get_system_info_response(cls, bytes_: bytes) -> ServerInfo:
        response: GetSystemInfoResponse = json.loads(bytes_)

        return ServerInfo(
            rss_version=response["rss_version"],
            sensor_count=response["sensor_count"],
            ticks_per_second=response["ticks_per_second"],
        )

    @classmethod
    def get_sensor_info_command(cls) -> bytes:
        return b'{"cmd":"get_sensor_info"}\n'

    @classmethod
    def get_sensor_info_response(cls, bytes_: bytes) -> list[int]:
        response: GetSensorInfoResponse = json.loads(bytes_)
        sensor_info = response["sensor_info"]

        return [
            i
            for i, connected_dict in enumerate(sensor_info, start=1)
            if connected_dict["connected"]
        ]

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

    @classmethod
    def setup_response(
        cls, bytes_: bytes, context_session_config: SessionConfig
    ) -> list[dict[int, Metadata]]:
        response: SetupResponse = json.loads(bytes_)
        metadata_groups = response["metadata"]

        result = []

        for metadata_group, config_group in zip(metadata_groups, context_session_config._groups):
            # OBS! This logic relies on insertion order.
            # Bugs may arise where meta-data is unaligned with configs.
            result.append(
                {
                    sensor_id: cls._metadata_from_dict(metadata_dict)
                    for metadata_dict, sensor_id in zip(metadata_group, config_group.keys())
                }
            )

        return result

    @classmethod
    def _metadata_from_dict(cls, metadata_dict: MetadataResponse) -> Metadata:
        data_type_str = metadata_dict["data_type"]
        data_type = SensorDataType[data_type_str.upper()]

        return Metadata(
            frame_data_length=metadata_dict["frame_data_length"],
            sweep_data_length=metadata_dict["sweep_data_length"],
            subsweep_data_offset=np.array(metadata_dict["subsweep_data_offset"]),
            subsweep_data_length=np.array(metadata_dict["subsweep_data_length"]),
            data_type=data_type,
        )
