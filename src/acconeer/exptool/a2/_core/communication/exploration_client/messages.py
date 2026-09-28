# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool._core.communication import Message, ParseError
from acconeer.exptool._core.int_16_complex import INT_16_COMPLEX, int16_complex_array_to_complex
from acconeer.exptool._core.version_parsing import parse_rss_version
from acconeer.exptool.a2._core.entities import GroupResult, Result, SessionConfig
from acconeer.exptool.a2._core.rx_major_frame_translation import translate_rx_major_frame


@attrs.frozen
class SetupResponse(Message):
    tick_period: int
    calibration: str
    update_period: float | None

    @classmethod
    def parse(cls, header: dict[str, t.Any], payload: bytes) -> te.Self:
        tick_period = header.get("tick_period")

        calibration_info = header.get("calibration_info")
        update_period = header.get("update_period")

        if tick_period is None or header.get("status") != "ok" or calibration_info is None:
            raise ParseError
        else:
            return cls(tick_period, calibration_info, update_period)


@attrs.frozen
class ResultMessage(Message):
    ticks: list[int]
    temperatures: list[int]
    data_saturated: list[list[bool]]
    sweep_rates: list[float | None]
    frame_delayeds: list[bool]
    calibration_temperatures: list[bool]
    calibration_neededs: list[bool]
    payload: bytes

    @classmethod
    def parse(cls, header: dict[str, t.Any], payload: bytes) -> te.Self:
        result_infos = header.get("result_info")
        if result_infos is None:
            raise ParseError

        return cls(
            ticks=[ri["tick"] for ri in result_infos],
            temperatures=[ri["temperature"] for ri in result_infos],
            data_saturated=[ri["data_saturated"] for ri in result_infos],
            sweep_rates=[
                ri["sweep_rate"] if ri["sweep_rate"] > 0 else None for ri in result_infos
            ],
            frame_delayeds=[ri["frame_delayed"] for ri in result_infos],
            calibration_temperatures=[ri["calibration_temperature"] for ri in result_infos],
            calibration_neededs=[ri["calibration_needed"] for ri in result_infos],
            payload=payload,
        )

    @staticmethod
    def _es_frames_are_tx_major(es_version: str) -> bool:
        _, server_version = parse_rss_version(es_version)
        _, switch_version = parse_rss_version("a211-v0.4.0-79-geb1dfc6010")
        res = bool(server_version >= switch_version)
        return res

    @classmethod
    def _frame_iter(
        cls, payload: bytes, config: SessionConfig, server_version: str
    ) -> t.Iterator[npt.NDArray[t.Any]]:
        complex_int16_payload = np.frombuffer(payload, dtype=INT_16_COMPLEX)
        complex_payload = int16_complex_array_to_complex(complex_int16_payload)

        for sensor_config in config.sensor_configs:
            points_in_sweep = sum(
                subsweep_config.num_points * subsweep_config.num_channels
                for subsweep_config in sensor_config.subsweeps
            )
            points_in_frame = points_in_sweep * sensor_config.sweeps_per_frame
            flat_frame = complex_payload[:points_in_frame]
            flat_frame.resize(sensor_config.sweeps_per_frame, points_in_sweep)
            frame = flat_frame

            if cls._es_frames_are_tx_major(server_version):
                yield frame
            else:
                rx_major_frame = frame
                yield translate_rx_major_frame(rx_major_frame, sensor_config)

            complex_payload = complex_payload[points_in_frame:]

    def create_result(self, config: SessionConfig, server_version: str) -> GroupResult:
        assert (
            len(config.sensor_configs)
            == len(self.ticks)
            == len(self.temperatures)
            == len(self.data_saturated)
            == len(self.sweep_rates)
            == len(self.frame_delayeds)
            == len(self.calibration_temperatures)
            == len(self.calibration_neededs)
        )

        return GroupResult(
            [
                Result(
                    temperature=temperature,
                    frame=frame,
                    tick=tick,
                    data_saturated=data_saturated,
                    measured_sweep_rate=sweep_rate,
                    frame_delayed=frame_delayed,
                    calibration_temperature=calibration_temperature,
                    calibration_needed=calibration_needed,
                )
                for frame, tick, temperature, data_saturated, sweep_rate, frame_delayed, calibration_temperature, calibration_needed in zip(
                    self._frame_iter(self.payload, config, server_version),
                    self.ticks,
                    self.temperatures,
                    self.data_saturated,
                    self.sweep_rates,
                    self.frame_delayeds,
                    self.calibration_temperatures,
                    self.calibration_neededs,
                )
            ]
        )
