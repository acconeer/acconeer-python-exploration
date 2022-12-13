# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import json
from typing import Any, Optional

from acconeer.exptool.a121._core.entities import PRF, IdleState, SensorCalibration, SessionConfig
from acconeer.exptool.a121._core.peripherals.communication.communication_protocol import (
    CommunicationProtocol,
)
from acconeer.exptool.a121._core.peripherals.communication.message import Message
from acconeer.exptool.a121._core.utils import map_over_extended_structure

from . import messages


class ExplorationProtocolError(Exception):
    pass


class ExplorationProtocol(CommunicationProtocol):
    end_sequence: bytes = b"\n"

    PRF_MAPPING = {
        PRF.PRF_19_5_MHz: "19_5_MHz",
        PRF.PRF_15_6_MHz: "15_6_MHz",
        PRF.PRF_13_0_MHz: "13_0_MHz",
        PRF.PRF_8_7_MHz: "8_7_MHz",
        PRF.PRF_6_5_MHz: "6_5_MHz",
        PRF.PRF_5_2_MHz: "5_2_MHz",
    }
    IDLE_STATE_MAPPING = {
        IdleState.DEEP_SLEEP: "deep_sleep",
        IdleState.SLEEP: "sleep",
        IdleState.READY: "ready",
    }

    @classmethod
    def parse_message(cls, header: dict[str, Any], payload: bytes) -> Message:
        PARSERS = [
            messages.EmptyResultMessage.parse,
            messages.SetBaudrateResponse.parse,
            messages.ErroneousMessage.parse,
            messages.LogMessage.parse,
            messages.ResultMessage.parse,
            messages.SystemInfoResponse.parse,
            messages.SensorInfoResponse.parse,
            messages.SetupResponse.parse,
            messages.StartStreamingResponse.parse,
            messages.StopStreamingResponse.parse,
        ]

        for parser in PARSERS:
            try:
                response = parser(header, payload)
            except messages.ParseError:
                pass
            else:
                return response

        raise RuntimeError(f"Could not parse response with header:\n{header}")

    @classmethod
    def get_system_info_command(cls) -> bytes:
        return b'{"cmd":"get_system_info"}\n'

    @classmethod
    def get_sensor_info_command(cls) -> bytes:
        return b'{"cmd":"get_sensor_info"}\n'

    @classmethod
    def start_streaming_command(cls) -> bytes:
        return b'{"cmd":"start_streaming"}\n'

    @classmethod
    def stop_streaming_command(cls) -> bytes:
        return b'{"cmd":"stop_streaming"}\n'

    @classmethod
    def set_baudrate_command(cls, baudrate: int) -> bytes:
        return b'{"cmd":"set_uart_baudrate","baudrate":' + str(baudrate).encode("ascii") + b"}\n"

    @classmethod
    def setup_command(
        cls,
        session_config: SessionConfig,
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> bytes:
        result = cls._setup_command_preprocessing(session_config)
        result["groups"] = cls._translate_groups_representation(result["groups"])
        if calibrations:
            result["calibration_info"] = []
            for sensor_id, calibration in calibrations.items():
                result["calibration_info"].append(
                    {"sensor_id": sensor_id, "data": calibration.data}
                )
        return (
            json.dumps(
                result,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("ascii")

    @classmethod
    def _setup_command_preprocessing(cls, session_config: SessionConfig) -> dict:
        result = session_config.to_dict()

        if session_config.update_rate is None:
            del result["update_rate"]

        # Exploration server is not interested in this.
        result.pop("extended")

        result["groups"] = map_over_extended_structure(cls._translate_prf_enums, result["groups"])
        result["groups"] = map_over_extended_structure(
            cls._translate_profile_enums, result["groups"]
        )
        result["groups"] = map_over_extended_structure(
            cls._translate_idle_state_enums, result["groups"]
        )
        result["groups"] = map_over_extended_structure(
            cls._translate_sentiel_values, result["groups"]
        )

        result["cmd"] = "setup"
        return result

    @classmethod
    def _translate_profile_enums(cls, sensor_config_dict: dict[str, Any]) -> dict[str, Any]:
        for subsweep_config_dict in sensor_config_dict["subsweeps"]:
            subsweep_config_dict["profile"] = subsweep_config_dict["profile"].value
        return sensor_config_dict

    @classmethod
    def _translate_prf_enums(cls, sensor_config_dict: dict[str, Any]) -> dict[str, Any]:
        for subsweep_config_dict in sensor_config_dict["subsweeps"]:
            subsweep_config_dict["prf"] = cls.PRF_MAPPING[subsweep_config_dict["prf"]]
        return sensor_config_dict

    @classmethod
    def _translate_idle_state_enums(cls, sensor_config_dict: dict[str, Any]) -> dict[str, Any]:
        sensor_config_dict["inter_frame_idle_state"] = cls.IDLE_STATE_MAPPING[
            sensor_config_dict["inter_frame_idle_state"]
        ]
        sensor_config_dict["inter_sweep_idle_state"] = cls.IDLE_STATE_MAPPING[
            sensor_config_dict["inter_sweep_idle_state"]
        ]
        return sensor_config_dict

    @classmethod
    def _translate_sentiel_values(cls, sensor_config_dict: dict[str, Any]) -> dict[str, Any]:
        """'sweep_rate' and 'frame_rate' has unlocked rate when they are = None.
        RSS's sentinel is 0.0 (zero)
        """
        sensor_config_dict["sweep_rate"] = sensor_config_dict["sweep_rate"] or 0.0
        sensor_config_dict["frame_rate"] = sensor_config_dict["frame_rate"] or 0.0
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
