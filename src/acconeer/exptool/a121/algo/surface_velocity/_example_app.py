# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities.configs.config_enums import IdleState, Profile
from acconeer.exptool.a121._core.utils import is_divisor_of, is_multiple_of
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    AlgoConfigBase,
    Controller,
    select_prf,
)

from ._processor import Processor, ProcessorConfig, ProcessorExtraResult


SPARSE_IQ_PPC = 24


def optional_profile_converter(profile: Optional[Profile]) -> Optional[Profile]:
    if profile is None:
        return None

    return Profile(profile)


def idle_state_converter(idle_state: IdleState) -> IdleState:
    return IdleState(idle_state)


@attrs.mutable(kw_only=True)
class ExampleAppConfig(AlgoConfigBase):
    surface_distance: float = attrs.field(default=1)
    """Perpendicular distance from the water surface to the sensor in meters."""

    sensor_angle: float = attrs.field(default=45)
    """
    Sensor angle in degrees. 0 degrees is defined as the sensor
    facing straight down to the surface.
    """

    num_points: int = attrs.field(default=4)
    """Number of data points in the measurement."""

    step_length: int = attrs.field(default=12)
    """Step length in points."""

    profile: Optional[a121.Profile] = attrs.field(
        default=None, converter=optional_profile_converter
    )
    """
    Sets the profile. If no argument is provided, the highest possible
    profile without interference of direct leakage is used to maximize SNR.
    """

    frame_rate: Optional[float] = attrs.field(default=None)
    """Frame rate in Hz."""

    sweep_rate: float = attrs.field(default=3000)
    """Sweep rate in Hz."""

    sweeps_per_frame: int = attrs.field(default=128)
    """Number of sweeps per frame."""

    hwaas: int = attrs.field(default=16)
    """Number of HWAAS."""

    double_buffering: bool = attrs.field(default=True)
    """Enables double buffering."""

    continuous_sweep_mode: bool = attrs.field(default=True)
    """Enables continuous sweep mode."""

    inter_frame_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.READY, converter=idle_state_converter
    )
    """Sets the inter frame idle state."""

    inter_sweep_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.READY, converter=idle_state_converter
    )
    """Sets the inter sweep idle state."""

    time_series_length: int = attrs.field(default=512)
    """Length of time series."""

    psd_lp_coeff: float = attrs.field(default=0.75)
    """Filter coefficient for the exponential filter of psd over time."""

    cfar_sensitivity: float = attrs.field(default=0.15)
    """Sensitivity of the CFAR threshold. Low sensitivity will set a high threshold."""

    cfar_guard: int = attrs.field(default=6)
    """
    Number of frequency bins around the point of interest that
    is omitted when calculating the CFAR threshold.
    """

    cfar_win: int = attrs.field(default=6)
    """
    Number of frequency bins next to the CFAR guard from
    which the threshold level will be calculated.
    """

    slow_zone: int = attrs.field(default=3)
    """Half size of the number of frequency bins that are regarded as the slow zone."""

    velocity_lp_coeff: float = attrs.field(default=0.98)
    """
    Filter coefficient for the exponential filter of the velocity estimate.
    """

    max_peak_interval_s: float = attrs.field(default=4)
    """
    Maximal number of seconds that is tolerated between
    peaks before the estimated velocity starts decreasing.
    """

    @step_length.validator
    def _validate_step_length(self, _: Any, step_length: int) -> None:
        if step_length is not None:
            if not (
                is_divisor_of(SPARSE_IQ_PPC, step_length)
                or is_multiple_of(SPARSE_IQ_PPC, step_length)
            ):
                raise ValueError(f"step_length must be a divisor or multiple of {SPARSE_IQ_PPC}")

    def _collect_validation_results(self) -> list[a121.ValidationResult]:

        return []


@attrs.frozen(kw_only=True)
class ExampleAppResult:
    velocity: float = attrs.field()
    """Estimated velocity."""

    distance_m: float = attrs.field()
    """Distance in meters used for the current velocity estimate."""

    processor_extra_result: ProcessorExtraResult = attrs.field()
    service_result: a121.Result = attrs.field()


class ExampleApp(Controller[ExampleAppConfig, ExampleAppResult]):
    MIN_DIST_M = {
        a121.Profile.PROFILE_1: None,
        a121.Profile.PROFILE_2: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_2],
        a121.Profile.PROFILE_3: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_3],
        a121.Profile.PROFILE_4: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_4],
        a121.Profile.PROFILE_5: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_5],
    }

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        example_app_config: ExampleAppConfig,
    ) -> None:
        super().__init__(client=client, config=example_app_config)
        self.sensor_id = sensor_id

        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, _algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            raise RuntimeError("Already started")

        sensor_config = self._get_sensor_config(self.config)
        self.session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        metadata = self.client.setup_session(self.session_config)
        assert isinstance(metadata, a121.Metadata)

        processor_config = self._get_processor_config(self.config)

        self.processor = Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            context=None,
        )

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                if _algo_group is None:
                    _algo_group = recorder.require_algo_group("surface_velocity")
                _record_algo_data(
                    _algo_group,
                    self.sensor_id,
                    self.config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        self.client.start_session(recorder)

        self.started = True

    @classmethod
    def _get_sensor_config(cls, config: ExampleAppConfig) -> a121.SensorConfig:
        optimal_distance = config.surface_distance / np.cos(np.radians(config.sensor_angle))
        optimal_point = int(np.floor(optimal_distance / APPROX_BASE_STEP_LENGTH_M))

        start_point = int(np.around(optimal_point - (config.num_points / 2) * config.step_length))
        if np.mod(config.num_points, 2) == 0:
            end_point = int(
                np.around(optimal_point + (config.num_points / 2 - 1) * config.step_length)
            )
        else:
            end_point = int(
                np.around(optimal_point + (config.num_points / 2) * config.step_length)
            )

        if config.profile is not None:
            profile = config.profile
        else:
            viable_profiles = [
                k
                for k, v in cls.MIN_DIST_M.items()
                if v is None or v <= start_point * APPROX_BASE_STEP_LENGTH_M
            ]
            profile = viable_profiles[-1]

        return a121.SensorConfig(
            profile=profile,
            start_point=start_point,
            num_points=config.num_points,
            step_length=config.step_length,
            prf=select_prf(end_point, profile),
            hwaas=config.hwaas,
            sweeps_per_frame=config.sweeps_per_frame,
            frame_rate=config.frame_rate,
            sweep_rate=config.sweep_rate,
            continuous_sweep_mode=config.continuous_sweep_mode,
            double_buffering=config.double_buffering,
            inter_frame_idle_state=config.inter_frame_idle_state,
            inter_sweep_idle_state=config.inter_sweep_idle_state,
        )

    @classmethod
    def _get_processor_config(cls, config: ExampleAppConfig) -> ProcessorConfig:
        return ProcessorConfig(
            surface_distance=config.surface_distance,
            sensor_angle=config.sensor_angle,
            time_series_length=config.time_series_length,
            slow_zone=config.slow_zone,
            psd_lp_coeff=config.psd_lp_coeff,
            cfar_guard=config.cfar_guard,
            cfar_win=config.cfar_win,
            cfar_sensitivity=config.cfar_sensitivity,
            velocity_lp_coeff=config.velocity_lp_coeff,
            max_peak_interval_s=config.max_peak_interval_s,
        )

    def get_next(self) -> ExampleAppResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return ExampleAppResult(
            velocity=processor_result.estimated_v,
            distance_m=processor_result.distance_m,
            processor_extra_result=processor_result.extra_result,
            service_result=result,
        )

    def update_config(self, config: ExampleAppConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            raise RuntimeError("Already stopped")

        recorder_result = self.client.stop_session()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    config: ExampleAppConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "example_app_config", config.to_json())


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, ExampleAppConfig]:
    sensor_id = algo_group["sensor_id"][()]
    config = ExampleAppConfig.from_json(algo_group["example_app_config"][()])
    return sensor_id, config
