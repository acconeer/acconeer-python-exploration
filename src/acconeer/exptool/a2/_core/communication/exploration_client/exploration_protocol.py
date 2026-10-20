# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import json
import typing as t

from acconeer.exptool._core.communication import CommunicationProtocol, Message
from acconeer.exptool._core.communication.communication_protocol import messages
from acconeer.exptool.a2._core.entities import PRF, SessionConfig

from .messages import ResultMessage, SetupResponse


class ExplorationProtocol(CommunicationProtocol[SessionConfig]):
    _PRF_MAPPING = {
        PRF.PRF_5_3_MHZ: "5_3_MHz",
        PRF.PRF_8_3_MHZ: "8_3_MHz",
        PRF.PRF_12_5_MHZ: "12_5_MHz",
        PRF.PRF_15_8_MHZ: "15_8_MHz",
        PRF.PRF_20_8_MHZ: "20_8_MHz",
        PRF.PRF_27_7_MHZ: "27_7_MHz",
    }

    @classmethod
    def setup_command(
        cls,
        config: SessionConfig,
        enable_diagnostics: bool = False,
        enable_log: str = "ERROR",
        calibration: t.Optional[str] = None,
    ) -> bytes:
        """The `setup` command."""
        setup_dict = {
            "cmd": "setup",
            "update_rate": config.update_rate or 0.0,
            "enable_log": enable_log,
            "enable_diagnostics": enable_diagnostics,
            "groups": [
                {
                    "config": {
                        "sweeps_per_frame": sensor_config.sweeps_per_frame,
                        "sweep_rate": sensor_config.sweep_rate or 0.0,
                        "frame_rate": sensor_config.frame_rate or 0.0,
                        "inter_frame_idle_state": sensor_config.inter_frame_idle_state.name.lower(),
                        "inter_sweep_idle_state": sensor_config.inter_sweep_idle_state.name.lower(),
                        "jitter_compensation": sensor_config.jitter_compensation,
                        "subsweeps": [
                            {
                                "start_point": subsweep_config.start_point,
                                "num_points": subsweep_config.num_points,
                                "step_length": subsweep_config.step_length,
                                "tx_antenna_mask": subsweep_config.tx_antenna_mask,
                                "rx_antenna_mask": subsweep_config.rx_antenna_mask,
                                "profile": int(subsweep_config.profile),
                                "prf": cls._PRF_MAPPING[subsweep_config.prf],
                                "hwaas_max": subsweep_config.hwaas_max,
                                "hwaas_min": subsweep_config.hwaas_min,
                                "hwaas_exponent": subsweep_config.hwaas_exponent,
                                "receiver_gain": subsweep_config.receiver_gain,
                                "enable_tx": subsweep_config.enable_tx,
                            }
                            for subsweep_config in sensor_config.subsweeps
                        ],
                    }
                }
                for sensor_config in config.sensor_configs
            ],
        }

        if calibration is not None:
            setup_dict["calibration_info"] = calibration

        return (
            json.dumps(
                setup_dict,
                separators=(",", ":"),
                ensure_ascii=True,
                indent=None,
            ).encode("ascii")
            + b"\n"
        )

    @classmethod
    def parse_message(cls, header: dict[str, t.Any], payload: bytes) -> Message:
        """Parses any supported Message given a header and a payload"""

        PARSERS = [
            messages.SetBaudrateResponse.parse,
            messages.ErroneousMessage.parse,
            messages.LogMessage.parse,
            ResultMessage.parse,
            messages.SystemInfoResponse.parse,
            SetupResponse.parse,
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

        msg = f"Could not parse response with header:\n{header}"
        raise RuntimeError(msg)
