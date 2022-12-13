# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import time
from typing import Any, Optional, Union

import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import (
    INT_16_COMPLEX,
    ClientInfo,
    Metadata,
    Profile,
    Result,
    ResultContext,
    SensorCalibration,
    SensorConfig,
    SensorInfo,
    ServerInfo,
    SessionConfig,
    SubsweepConfig,
)
from acconeer.exptool.a121._core.mediators import ClientBase, ClientError, Recorder
from acconeer.exptool.a121._core.utils import unextend
from acconeer.exptool.a121._rate_calc import _RateCalculator, _RateStats

from .utils import get_calibrations_provided


class MockClient(ClientBase):

    TICKS_PER_SECOND = 1000000
    CALIBRATION_TEMPERATURE = 25
    BASE_STEP_LENGTH_M = 0.0025
    SENSOR_COUNT = 5
    SENSOR_OBJECTS = {
        1: {"distance_mm": 500, "peak_amplitude": 10000, "phase": 0.5},
        2: {"distance_mm": 1000, "peak_amplitude": 8000, "phase": 1.0},
        3: {"distance_mm": 1500, "peak_amplitude": 6000, "phase": 1.5},
        4: {"distance_mm": 2000, "peak_amplitude": 4000, "phase": 2.0},
        5: {"distance_mm": 2500, "peak_amplitude": 2000, "phase": 2.5},
    }
    FWHM = {
        Profile.PROFILE_1: 16,
        Profile.PROFILE_2: 30,
        Profile.PROFILE_3: 54,
        Profile.PROFILE_4: 76,
        Profile.PROFILE_5: 132,
    }
    DIRECT_LEAKAGE_PHASE = 0.0
    DIRECT_LEAKAGE_AMPLITUDE = 2000
    NOISE_AMPLITUDE = 20
    MOCK_SERVER_INFO = ServerInfo(
        rss_version=f"a121-v{a121.SDK_VERSION}",
        sensor_count=SENSOR_COUNT,
        ticks_per_second=TICKS_PER_SECOND,
        hardware_name="Mock-system",
        sensor_infos={
            1: SensorInfo(connected=True, serial="SN1"),
            2: SensorInfo(connected=True, serial="SN2"),
            3: SensorInfo(connected=True, serial="SN3"),
            4: SensorInfo(connected=True, serial="SN4"),
            5: SensorInfo(connected=True, serial="SN5"),
        },
    )

    _client_info: ClientInfo
    _connected: bool
    _session_is_started: bool
    _recorder: Optional[Recorder]
    _metadata: Optional[list[dict[int, Metadata]]]
    _sensor_calibrations: Optional[dict[int, SensorCalibration]]
    _session_config: Optional[SessionConfig]
    _calibrations_provided: dict[int, bool]
    _rate_stats_calc: Optional[_RateCalculator]
    _start_time: float

    def __init__(self, client_info: ClientInfo) -> None:
        self._calibrations_provided = {}
        self._client_info = client_info
        self._connected = False
        self._metadata = None
        self._rate_stats_calc = None
        self._recorder = None
        self._sensor_calibrations = None
        self._session_config = None
        self._session_is_started = False
        self._start_time = time.monotonic()

    def _assert_connected(self) -> None:
        if not self.connected:
            raise ClientError("Client is not connected.")

    def _assert_session_setup(self) -> None:
        self._assert_connected()
        if not self.session_is_setup:
            raise ClientError("Session is not set up.")

    def _assert_session_started(self) -> None:
        self._assert_session_setup()
        if not self.session_is_started:
            raise ClientError("Session is not started.")

    @classmethod
    def _sensor_config_to_metadata(
        cls, sensor_config: SensorConfig, update_rate: Optional[float]
    ) -> Metadata:
        subsweep_data_length = []
        subsweep_data_offset = []
        sweep_data_length = 0
        tick_period = 0 if update_rate is None else int(cls.TICKS_PER_SECOND / update_rate)
        for subsweep in sensor_config.subsweeps:
            subsweep_data_length.append(subsweep.num_points)
            subsweep_data_offset.append(sweep_data_length)
            sweep_data_length += subsweep.num_points
        return Metadata(
            frame_data_length=sensor_config._sweeps_per_frame * sweep_data_length,
            sweep_data_length=sweep_data_length,
            subsweep_data_length=np.array(subsweep_data_length),
            subsweep_data_offset=np.array(subsweep_data_offset),
            max_sweep_rate=100000,
            tick_period=tick_period,
            calibration_temperature=cls.CALIBRATION_TEMPERATURE,
            base_step_length_m=cls.BASE_STEP_LENGTH_M,
        )

    @classmethod
    def _session_config_to_metadata(cls, config: SessionConfig) -> list[dict[int, Metadata]]:
        metadata_list = []
        for group in config.groups:
            metadata_dict = {}
            for sensor_id, sensor_config in group.items():
                metadata_dict[sensor_id] = cls._sensor_config_to_metadata(
                    sensor_config, config.update_rate
                )
            metadata_list.append(metadata_dict)
        return metadata_list

    @classmethod
    def _get_mock_data(cls, sensor_id: int, subsweep: SubsweepConfig) -> npt.NDArray[np.complex_]:

        noise: npt.NDArray[np.complex_] = np.random.normal(
            0, cls.NOISE_AMPLITUDE, size=2 * subsweep.num_points
        ).view(np.complex_)

        if not subsweep.enable_tx:
            return noise

        object_distance = cls.SENSOR_OBJECTS[sensor_id]["distance_mm"] / (
            1000 * cls.BASE_STEP_LENGTH_M
        )
        peak_amplitude = cls.SENSOR_OBJECTS[sensor_id]["peak_amplitude"]
        phase = cls.SENSOR_OBJECTS[sensor_id]["phase"]
        points = subsweep.start_point + np.arange(subsweep.num_points) * subsweep.step_length
        std = cls.FWHM[subsweep.profile] / 2.355
        direct_leakage: npt.NDArray[np.complex_] = (
            np.exp(1j * cls.DIRECT_LEAKAGE_PHASE)
            * cls.DIRECT_LEAKAGE_AMPLITUDE
            * np.exp(-((points) ** 2) / (2 * std**2))
        )

        if subsweep.enable_loopback:
            return direct_leakage + noise

        signal: npt.NDArray[np.complex_] = (
            np.exp(1j * phase)
            * peak_amplitude
            * np.exp(-((points - object_distance) ** 2) / (2 * std**2))
        )

        return direct_leakage + signal + noise

    @classmethod
    def _sensor_config_to_frame(
        cls, sensor_id: int, sensor_config: SensorConfig, metadata: Metadata
    ) -> npt.NDArray:
        frame: npt.NDArray = np.ndarray(
            shape=(sensor_config._sweeps_per_frame, metadata.sweep_data_length),
            dtype=INT_16_COMPLEX,
        )
        for sweep in range(0, sensor_config._sweeps_per_frame):
            sweep_offset = 0
            for subsweep in sensor_config.subsweeps:
                subsweep_data = cls._get_mock_data(sensor_id, subsweep)
                for idx, point in enumerate(subsweep_data):
                    frame[sweep][sweep_offset + idx]["real"] = point.real
                    frame[sweep][sweep_offset + idx]["imag"] = point.imag
                sweep_offset += subsweep.num_points
        return frame

    def _sensor_config_to_result(self, sensor_id: int, sensor_config: SensorConfig) -> Result:
        metadata = self._sensor_config_to_metadata(sensor_config, update_rate=None)
        return Result(
            data_saturated=False,
            frame_delayed=False,
            calibration_needed=False,
            temperature=int(self.CALIBRATION_TEMPERATURE + np.random.normal(0, 2)),
            tick=int((time.monotonic() - self._start_time) * self.TICKS_PER_SECOND),
            frame=self._sensor_config_to_frame(sensor_id, sensor_config, metadata),
            context=ResultContext(ticks_per_second=self.TICKS_PER_SECOND, metadata=metadata),
        )

    def _session_config_to_result(self, config: SessionConfig) -> list[dict[int, Result]]:
        result_list = []
        for group in config.groups:
            result_dict = {}
            for sensor_id, sensor_config in group.items():
                result_dict[sensor_id] = self._sensor_config_to_result(sensor_id, sensor_config)
            result_list.append(result_dict)
        return result_list

    def connect(self) -> None:
        if not self._connected:
            self._connected = True
        else:
            raise ClientError("Client is already connected")

    def setup_session(
        self,
        config: Union[SensorConfig, SessionConfig],
        calibrations: Optional[dict[int, SensorCalibration]] = None,
    ) -> Union[Metadata, list[dict[int, Metadata]]]:
        if self.session_is_started:
            raise ClientError("Session is currently running, can't setup.")

        if isinstance(config, SensorConfig):
            config = SessionConfig(config)

        config.validate()

        self._calibrations_provided = get_calibrations_provided(config, calibrations)
        self._session_config = config
        self._metadata = self._session_config_to_metadata(config)

        self._sensor_calibrations = {}
        for group in config.groups:
            for sensor_id, sensor_config in group.items():
                self._sensor_calibrations[sensor_id] = SensorCalibration(
                    temperature=25,
                    data="mocked calibration",
                )

        if self.session_config.extended:
            return self._metadata
        else:
            return unextend(self._metadata)

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        self._assert_session_setup()

        if self.session_is_started:
            raise ClientError("Session is already started.")

        if recorder is not None:
            calibrations_provided: Optional[dict[int, bool]] = self.calibrations_provided
            try:
                calibrations = self.calibrations
            except ClientError:
                calibrations = None
                calibrations_provided = None

            self._recorder = recorder
            self._recorder._start(
                client_info=self.client_info,
                extended_metadata=self.extended_metadata,
                server_info=self.server_info,
                session_config=self.session_config,
                calibrations=calibrations,
                calibrations_provided=calibrations_provided,
            )

        self._session_is_started = True
        assert self._metadata is not None
        self._rate_stats_calc = _RateCalculator(self.session_config, self._metadata)
        self._start_time = time.monotonic()

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        self._assert_session_started()

        if self._metadata is None:
            raise RuntimeError(f"{self} has no metadata")

        if self._session_config is None:
            raise RuntimeError(f"{self} has no session config")

        extended_results = self._session_config_to_result(self.session_config)

        if self._recorder is not None:
            self._recorder._sample(extended_results)

        assert self._rate_stats_calc is not None
        self._rate_stats_calc.update(extended_results)

        if self.session_config.extended:
            return extended_results
        else:
            return unextend(extended_results)

    def stop_session(self) -> Any:
        self._assert_session_started()
        self._session_is_started = False

        if self._recorder is None:
            recorder_result = None
        else:
            recorder_result = self._recorder._stop()
            self._recorder = None

        self._rate_stats_calc = None

        return recorder_result

    def disconnect(self) -> None:
        if not self._connected:
            raise ClientError("Client is already disconnected")

        if self.session_is_started:
            _ = self.stop_session()

        self._metadata = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def session_is_setup(self) -> bool:
        return self._metadata is not None

    @property
    def session_is_started(self) -> bool:
        return self._session_is_started

    @property
    def server_info(self) -> ServerInfo:
        self._assert_connected()
        return self.MOCK_SERVER_INFO

    @property
    def client_info(self) -> ClientInfo:
        return self._client_info

    @property
    def session_config(self) -> SessionConfig:
        self._assert_session_setup()
        assert self._session_config is not None  # Should never happen if session is setup
        return self._session_config

    @property
    def extended_metadata(self) -> list[dict[int, Metadata]]:
        self._assert_session_setup()
        assert self._metadata is not None  # Should never happen if session is setup
        return self._metadata

    @property
    def calibrations(self) -> dict[int, SensorCalibration]:
        self._assert_session_setup()

        if not self._sensor_calibrations:
            raise ClientError("Server did not provide calibration")

        return self._sensor_calibrations

    @property
    def calibrations_provided(self) -> dict[int, bool]:
        return self._calibrations_provided

    @property
    def _rate_stats(self) -> _RateStats:
        self._assert_session_started()
        assert self._rate_stats_calc is not None
        return self._rate_stats_calc.stats
