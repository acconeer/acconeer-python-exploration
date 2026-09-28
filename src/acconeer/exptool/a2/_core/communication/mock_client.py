# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import time
import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool._core.communication.client import ClientCreationError, ClientError
from acconeer.exptool._core.entities import ClientInfo, MockInfo
from acconeer.exptool.a2 import SDK_VERSION
from acconeer.exptool.a2._core.entities import (
    AntennaArray,
    GroupResult,
    Metadata,
    Result,
    ServerInfo,
    SessionConfig,
    SubsweepConfig,
)

from .client import Client as A2Client


BASE_STEP_LENGTH = 2.5e-3


_MOCK_TICKS_PER_SECOND = 10000


class MockClient(A2Client, register=True):
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
            raise ClientCreationError

        if mock in [False, None]:
            raise ClientCreationError

        return cls(client_info=ClientInfo(mock=MockInfo()))

    def __init__(self, client_info: ClientInfo) -> None:
        super().__init__(client_info)
        self._data_generator: t.Iterator[GroupResult] = iter([])

    def setup_session(self, config: SessionConfig, calibration: str | None = None) -> Metadata:
        self._config = config
        self._calibration_provided = calibration is not None

        if self._config.update_rate is None:
            tick_period = 0
        else:
            tick_period = int(_MOCK_TICKS_PER_SECOND / self._config.update_rate)

        self._metadata = Metadata(
            tick_period=tick_period,
            sensor_calibration=calibration or "MOCK",
            update_period=None,
        )
        return self._metadata

    def start_session(self) -> None:
        self._assert_session_setup()
        assert self._config is not None

        if self.session_is_started:
            msg = "Session is already started"
            raise ClientError(msg)

        self._data_generator = get_data_generator(
            self._config, temperature=21, tick_period=self.tick_period
        )
        self._recorder_start_session()
        self._session_is_started = True

    def _get_next_group_result(self) -> GroupResult:
        return next(self._data_generator)

    @property
    def connected(self) -> bool:
        return not self._closed

    @property
    def server_info(self) -> ServerInfo:
        self._assert_connected()

        return ServerInfo(
            rss_version=f"a2-v{SDK_VERSION}",
            ticks_per_second=_MOCK_TICKS_PER_SECOND,
            hardware_name="exploration_tool",
            sensor_serial="mock_serial",
            max_baudrate=None,
        )

    def close(self) -> None:
        if self._closed:
            return

        if self.session_is_started:
            self.stop_session()
            self._recorder_stop_session()

        self._metadata = None
        self._closed = True
        self._update_period = None


@attrs.frozen
class _MockObject:
    """A mock object with perfect reflectivity back towards the sensor"""

    radius_m: float
    _position_f: t.Callable[[int], tuple[float, float, float]]

    def position(self, tick: int) -> tuple[float, float, float]:
        """The 3D position in meters of the object."""
        return self._position_f(tick)

    @staticmethod
    def find_first_impulse(array: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
        """Finds and keeps the first impulse in an array

        >>> _MockObject.find_first_impulse(np.array([0, 0, 0, 0, 1, 1, 1]))
        array([0, 0, 0, 0, 1, 0, 0])
        >>> _MockObject.find_first_impulse(np.array([0, 0, 1, 1, 1, 0, 0]))
        array([0, 0, 1, 0, 0, 0, 0])
        >>> _MockObject.find_first_impulse(np.array([0]))
        array([0])
        >>> _MockObject.find_first_impulse(np.array([1]))
        array([1])
        >>> _MockObject.find_first_impulse(np.array([1, 1, 0, 0, 0, 1, 1]))
        array([1, 0, 0, 0, 0, 0, 0])
        """
        if len(array) == 1:
            return array

        if array[0]:
            result = np.zeros_like(array)
            result[0] = True
            return result

        shifted_array = np.roll(array, shift=1)
        shifted_array[0] = array[0]
        return (array ^ shifted_array) & array

    def collision_with_ray(self, ray_az: float, ray_el: float, tick: int) -> float | None:
        """
        Returns the distance in meter a ray cast from origin with specified angles (in radians)
        collides with this object (if it collides)

        If the object is along the x-axis, a ray cast with angles 0, pi / 2 should hit.
        >>> obj = _MockObject(radius_m=0.1, position_f=lambda _: (1, 0, 0))
        >>> obj.collision_with_ray(0, np.pi / 2, tick=0)
        0.9

        If the object is along the y-axis, a ray cast with angles pi / 2, pi / 2 should hit.
        >>> obj = _MockObject(radius_m=0.1, position_f=lambda _: (0, 1, 0))
        >>> obj.collision_with_ray(np.pi / 2, np.pi / 2, tick=0)
        0.9

        If the object is along the z-axis, a ray cast with angles 0, 0 should hit at 0.9 meters
        >>> obj = _MockObject(radius_m=0.1, position_f=lambda _: (0, 0, 1))
        >>> obj.collision_with_ray(0, 0, tick=0)
        0.9

        The same object position should miss with an az angle of pi (negative x direction)
        >>> obj.collision_with_ray(np.pi, np.pi / 2, tick=0)

        """
        center_x, center_y, center_z = self.position(tick)
        object_distance = np.sqrt(sum([center_x**2, center_y**2, center_z**2]))
        distances_m = np.arange(0, object_distance, 2.5e-3)

        ray_xs = distances_m * np.sin(ray_el) * np.cos(ray_az)
        ray_ys = distances_m * np.sin(ray_el) * np.sin(ray_az)
        ray_zs = distances_m * np.cos(ray_el)

        distances_to_center = np.sqrt(
            (ray_xs - center_x) ** 2 + (ray_ys - center_y) ** 2 + (ray_zs - center_z) ** 2
        )

        for distance_from_origin, distance_to_center in zip(distances_m, distances_to_center):
            if distance_to_center <= self.radius_m:
                return float(distance_from_origin)

        return None

    def data_for_angle(
        self, config: SubsweepConfig, az: float, el: float, tick: int
    ) -> npt.NDArray[np.complex128]:
        """Get noise-free mock data, for a subsweep, for the passed angles (in radians)"""
        if collision_distance := self.collision_with_ray(az, el, tick):
            points = np.arange(0, config.num_points) * config.step_length + config.start_point
            distances_m = points * BASE_STEP_LENGTH
            amplitudes = np.array(
                [
                    max(
                        0,
                        4000 - abs(100000 * (distance_m - collision_distance)),
                    )
                    for distance_m in distances_m
                    for _ in range(config.num_channels)
                ],
                dtype=float,
            )

            steering_vector = AntennaArray.AP212.get_steering_vector(
                az, el, config.rx_antenna_mask, config.tx_antenna_mask, profile=config.profile
            )

            # Avoid having NaN in steering vectors where is not defined
            steering_vector = np.nan_to_num(steering_vector, nan=1.0)

            return amplitudes * np.tile(steering_vector, config.num_points)
        else:
            return np.zeros(config.num_points * config.num_channels)  # type: ignore[return-value]


def object_position(tick: int) -> tuple[float, float, float]:
    return (
        1.0,
        1.0 * np.sin(2 * np.pi * tick / _MOCK_TICKS_PER_SECOND / 40),
        0.0,
    )


def get_data_generator(
    config: SessionConfig, temperature: int, tick_period: int
) -> t.Iterator[GroupResult]:
    mock_object = _MockObject(radius_m=0.2, position_f=object_position)

    start_time = previous_time = time.perf_counter()
    time_between_results = 1 / (config.update_rate or 100.0)

    while True:
        seconds_until_next = previous_time + time_between_results - time.perf_counter()
        if seconds_until_next > 0:
            time.sleep(seconds_until_next)

        previous_time = time.perf_counter()
        seconds_since_start = previous_time - start_time
        ticks_since_start = int(seconds_since_start * _MOCK_TICKS_PER_SECOND)

        results: list[Result] = []

        for sensor_config in config.sensor_configs:
            # Noise-free per angle at a fixed tick, so it's the same for every sweep in
            # this frame; computed once per subsweep instead of once per sweep.
            subsweep_signals = [
                sum(
                    mock_object.data_for_angle(
                        config=subsweep_config,
                        az=az,
                        el=el,
                        tick=ticks_since_start,
                    )
                    for az in np.linspace(-np.pi / 2, np.pi / 2, 20)
                    for el in np.linspace(0, np.pi, 20)
                )
                for subsweep_config in sensor_config.subsweeps
            ]

            frame: list[list[np.complex128]] = []
            for _ in range(sensor_config.sweeps_per_frame):
                sweep: list[np.complex128] = []

                for subsweep_signal in subsweep_signals:
                    subsweep_noise = 100 * (
                        np.random.default_rng().standard_normal(*np.shape(subsweep_signal))
                        + 1j * np.random.default_rng().standard_normal(*np.shape(subsweep_signal))
                    )

                    sweep.extend(np.asarray(subsweep_signal + subsweep_noise, dtype=np.complex128))

                frame.append(sweep)
            results.append(
                Result(
                    temperature=temperature,
                    data_saturated=[False] * len(sensor_config.subsweeps),
                    tick=ticks_since_start,
                    frame=np.array(frame).round(),
                    measured_sweep_rate=sensor_config.sweep_rate,
                    frame_delayed=False,
                    calibration_temperature=25,
                    calibration_needed=False,
                )
            )

        yield GroupResult(
            results=results,
        )
