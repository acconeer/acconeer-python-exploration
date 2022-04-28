from __future__ import annotations

import json
from typing import Any, Literal, Tuple, Union

import attrs
import numpy as np

from acconeer.exptool.a121._core._entities import (
    PRF,
    Metadata,
    Result,
    ResultContext,
    SensorDataType,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core._mediators import CommunicationProtocol
from acconeer.exptool.a121._core._utils import map_over_extended_structure

from typing_extensions import TypedDict


class Response(TypedDict):
    status: Union[
        Literal["ok"], Literal["error"], Literal["start"], Literal["stop"], Literal["end"]
    ]


class SystemInfo(TypedDict):
    rss_version: str
    sensor: str
    sensor_count: int
    ticks_per_second: int
    hw: str


class GetSystemInfoResponse(Response):
    system_info: SystemInfo


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


class ResultInfoDict(TypedDict):
    tick: int
    data_saturated: bool
    frame_delayed: bool
    calibration_needed: bool
    temperature: int


class GetNextHeader(Response):
    result_info: list[list[ResultInfoDict]]
    payload_size: int


class ExplorationProtocolError(Exception):
    pass


class ExplorationProtocol(CommunicationProtocol):
    end_sequence: bytes = b"\n"

    PRF_MAPPING = {
        PRF.PRF_19_5_MHz: "19_5_MHz",
        PRF.PRF_13_0_MHz: "13_0_MHz",
        PRF.PRF_8_7_MHz: "8_7_MHz",
        PRF.PRF_6_5_MHz: "6_5_MHz",
    }

    @classmethod
    def get_system_info_command(cls) -> bytes:
        return b'{"cmd":"get_system_info"}\n'

    @classmethod
    def get_system_info_response(cls, bytes_: bytes) -> ServerInfo:
        response: GetSystemInfoResponse = json.loads(bytes_)

        try:
            system_info = response["system_info"]
            return ServerInfo(
                rss_version=system_info["rss_version"],
                sensor_count=system_info["sensor_count"],
                ticks_per_second=system_info["ticks_per_second"],
            )
        except KeyError as ke:
            raise ExplorationProtocolError(
                f"Could not parse 'get_system_info' response. Response: {response}"
            ) from ke

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

        result["groups"] = map_over_extended_structure(cls._translate_prf_enums, result["groups"])

        result["cmd"] = "setup"
        result["groups"] = cls._translate_groups_representation(result["groups"])
        return (
            json.dumps(
                result,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("ascii")

    @classmethod
    def _translate_prf_enums(cls, sensor_config_dict: dict[str, Any]) -> dict[str, Any]:
        for subsweep_config_dict in sensor_config_dict["subsweeps"]:
            subsweep_config_dict["prf"] = cls.PRF_MAPPING[subsweep_config_dict["prf"]]
        return sensor_config_dict

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

    @classmethod
    def start_streaming_command(cls) -> bytes:
        return b'{"cmd":"start_streaming"}\n'

    @classmethod
    def start_streaming_response(cls, bytes_: bytes) -> bool:
        response: Response = json.loads(bytes_)
        return response["status"] == "start"

    @classmethod
    def stop_streaming_command(cls):
        return b'{"cmd":"stop_streaming"}\n'

    @classmethod
    def stop_streaming_response(cls, bytes_: bytes) -> bool:
        response: Response = json.loads(bytes_)
        return response["status"] == "stop"

    @classmethod
    def get_next_header(
        cls, bytes_: bytes, extended_metadata: list[dict[int, Metadata]], ticks_per_second: int
    ) -> Tuple[int, list[dict[int, Result]]]:
        header_dict: GetNextHeader = json.loads(bytes_)
        payload_size = header_dict["payload_size"]

        extended_partial_results = []
        partial_result_groups = header_dict["result_info"]

        for partial_result_group, metadata_group in zip(partial_result_groups, extended_metadata):
            inner_result = {}
            for partial_result_dict, (sensor_id, metadata) in zip(
                partial_result_group, metadata_group.items()
            ):
                inner_result[sensor_id] = cls._create_partial_result(
                    **partial_result_dict, metadata=metadata, ticks_per_second=ticks_per_second
                )

            extended_partial_results.append(inner_result)

        return payload_size, extended_partial_results

    @classmethod
    def _create_partial_result(
        cls,
        *,
        tick: int,
        ticks_per_second: int,
        data_saturated: bool,
        temperature: int,
        frame_delayed: bool,
        calibration_needed: bool,
        metadata: Metadata,
    ) -> Result:
        return Result(
            tick=tick,
            data_saturated=data_saturated,
            frame=np.array([0]),
            temperature=temperature,
            frame_delayed=frame_delayed,
            calibration_needed=calibration_needed,
            context=ResultContext(
                metadata=metadata,
                ticks_per_second=ticks_per_second,
            ),
        )

    @classmethod
    def get_next_payload(
        cls, bytes_: bytes, partial_results: list[dict[int, Result]]
    ) -> list[dict[int, Result]]:
        start = 0
        for partial_group in partial_results:
            for sensor_id, partial_result in partial_group.items():
                metadata = partial_result._context.metadata
                data_type = metadata._data_type
                end = start + metadata.frame_data_length * 4

                raw_frame = bytes_[start:end]
                np_frame = np.frombuffer(raw_frame, dtype=data_type.value)
                partial_group[sensor_id] = attrs.evolve(partial_result, frame=np_frame)
                start += end
        return partial_results
