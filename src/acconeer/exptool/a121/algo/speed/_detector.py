# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities.configs.config_enums import IdleState, Profile
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121._perf_calc import get_sample_duration
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    PERCEIVED_WAVELENGTH,
    AlgoConfigBase,
    Controller,
    select_prf,
)

from ._processors import Processor, ProcessorConfig


SPARSE_IQ_PPC = 24

NUM_SEGMENTS = 4  # should be a power of 2


def optional_profile_converter(profile: Optional[Profile]) -> Optional[Profile]:
    if profile is None:
        return None

    return Profile(profile)


def idle_state_converter(idle_state: IdleState) -> IdleState:
    return IdleState(idle_state)


@attributes_doc
@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_point: int = attrs.field(default=200)
    """Start point of measurement interval."""

    num_points: int = attrs.field(default=1)
    """Number of points to measure."""

    step_length: Optional[int] = attrs.field(
        default=None,
        validator=attrs.validators.optional(a121.SubsweepConfig.step_length_validator),
    )
    """Step length between points."""

    profile: Optional[a121.Profile] = attrs.field(
        default=None, converter=optional_profile_converter
    )
    """
    Sets the profile. If no argument is provided, the highest possible
    profile without interference of direct leakage is used to maximize SNR.
    """
    frame_rate: Optional[float] = attrs.field(default=None)
    """Frame rate in Hz."""

    num_bins: int = attrs.field(default=50)
    """Determines the resolution in m/s by max_speed/num_bins."""

    sweep_rate: Optional[int] = attrs.field(default=None)
    """Sweep rate in Hz."""

    hwaas: Optional[int] = attrs.field(default=None)
    """Number of HWAAS."""

    max_speed: float = attrs.field(default=10.0)
    """Max detectable speed in m/s."""

    threshold: float = attrs.field(default=100.0)
    """
    Peak relative height to median scaled PSD.
    E.g., 10.0 indicates that we need to have 10 times the median value to trigger.
    """

    @classmethod
    def _get_min_sweep_rate(cls, max_speed: float) -> int:
        """
        Calculates the min sweep rate in Hz based on the desired max speed.
        Inverse to _get_max_speed
        """
        # max speed is half half wavelength over sample time (1/sample frequency).
        # Oversample by 10%
        min_sample_freq = 1.1 * 2 * max_speed / PERCEIVED_WAVELENGTH

        sample_freq = int(np.ceil(min_sample_freq))

        return sample_freq

    @classmethod
    def _get_max_speed(cls, sweep_rate: int) -> float:
        """
        Calculates the max speed in m/s based on the desired sweep_rate.
        Inverse to _get_min_sweep_rate
        """
        max_speed = sweep_rate * PERCEIVED_WAVELENGTH / (1.1 * 2)

        return max_speed

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        min_sweep_rate = self._get_min_sweep_rate(self.max_speed)
        frame_rate = self.frame_rate
        sweep_rate = self.sweep_rate
        sweeps_per_frame = self.num_bins * NUM_SEGMENTS

        max_frame_rate = None
        profile_3_direct_leakage_end = int(
            2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_3] / PERCEIVED_WAVELENGTH
        )

        if self.start_point < profile_3_direct_leakage_end:
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "start_point",
                    "Range includes direct leakage, risk for missed detection",
                )
            )

        if self.num_points == 1 and self.step_length is not None:
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "step_length",
                    "Step length is not used when sampling a single point.",
                )
            )

        if self.num_points > 1:
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "num_points",
                    "Several depths measured, " "measures of different objects might be reported.",
                )
            )

        if self.profile == a121.Profile.PROFILE_1 or self.profile == a121.Profile.PROFILE_2:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "profile",
                    "Only Profile 3,4 or 5 is supported.",
                )
            )

        if sweep_rate is not None:
            max_frame_rate = sweep_rate / sweeps_per_frame
            if sweep_rate < min_sweep_rate:
                validation_results.append(
                    a121.ValidationError(
                        self,
                        "sweep_rate",
                        "Max speed measurement too high with set sweep rate."
                        " Increase sweep rate or lower max speed.",
                    )
                )

        if frame_rate is not None and max_frame_rate is not None and frame_rate > max_frame_rate:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "frame_rate",
                    f"Frame rate is too high, max frame rate is approx {max_frame_rate}",
                )
            )

        # Figure out buffer size and warn about that.

        buffer_size = self.num_points * sweeps_per_frame
        if buffer_size > 4095:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "num_bins",
                    f"Buffer size too large ({buffer_size}). Reduce num points or num_bins.",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class DetectorMetadata:
    start_m: float = attrs.field()
    """Actual start point of measurement in meters"""

    step_length_m: float = attrs.field()
    """Actual step length between each data point of the measurement in meters"""

    num_points: int = attrs.field()
    """The number of data points in the measurement"""

    profile: a121.Profile = attrs.field()
    """Profile used for measurement"""


@attrs.frozen(kw_only=True)
class DetectorExtraResult:
    psd: npt.NDArray[np.float64]
    """Full Power Spectral Density from the DFT"""

    velocities: npt.NDArray[np.float64]
    """The frequency bins interpreted as speeds"""

    actual_thresholds: npt.NDArray[np.float64]
    """The thresholds that was used in this frame"""


@attrs.frozen(kw_only=True)
class DetectorResult:
    speed_per_depth: npt.NDArray[np.float64]
    """The measured speed for each depth"""

    extra_result: DetectorExtraResult
    """Detailed results, used for plotting"""

    @property
    def max_speed(self) -> np.float64:
        return max(np.min(self.speed_per_depth), np.max(self.speed_per_depth), key=np.abs)


class Detector(Controller[DetectorConfig, DetectorResult]):
    MIN_DIST_M = {
        a121.Profile.PROFILE_3: None,
        a121.Profile.PROFILE_4: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_4],
        a121.Profile.PROFILE_5: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_5],
    }

    DEFAULT_STEP_LENGTH = {
        a121.Profile.PROFILE_1: 12,
        a121.Profile.PROFILE_2: 24,
        a121.Profile.PROFILE_3: 48,
        a121.Profile.PROFILE_4: 72,
        a121.Profile.PROFILE_5: 120,
    }

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        detector_config: DetectorConfig,
    ) -> None:
        super().__init__(client=client, config=detector_config)
        self.sensor_id = sensor_id
        self.detector_metadata: Optional[DetectorMetadata] = None

        self.started = False
        self.config = detector_config
        self.timing = 0.0

    def start(
        self,
        recorder: Optional[a121.Recorder] = None,
        _algo_group: Optional[h5py.Group] = None,
    ) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        sensor_config = self._get_sensor_config(self.config)
        self.session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        metadata = self.client.setup_session(self.session_config)
        assert isinstance(metadata, a121.Metadata)

        self.processor_config = self._get_processor_config(self.config)
        self.processor = Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=self.processor_config,
        )

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                if _algo_group is None:
                    _algo_group = recorder.require_algo_group("speed_detector")
                _record_algo_data(
                    _algo_group,
                    self.sensor_id,
                    self.config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")
            self.client.attach_recorder(recorder)

        self.detector_metadata = DetectorMetadata(
            start_m=sensor_config.start_point * APPROX_BASE_STEP_LENGTH_M,
            step_length_m=metadata.base_step_length_m * sensor_config.step_length,
            num_points=sensor_config.num_points,
            profile=sensor_config.profile,
        )
        self.client.start_session()

        self.started = True

    @classmethod
    def _get_max_hwaas(
        cls, sweep_rate: int, num_points: int, prf: a121.PRF, profile: a121.Profile
    ) -> int:
        sample_duration = get_sample_duration(prf=prf, profile=profile)

        MAGIC_OVERHEAD_S = 2 * 1e-6  # Constant added in rss "for good measure"

        # 0.98 is also an added percentage from rss that is accounted for here
        max_sweep_duration = (
            ((1.0 / sweep_rate) - MAGIC_OVERHEAD_S) * 0.98 / (num_points * sample_duration)
        )
        max_hwaas = int(np.floor(max_sweep_duration - 4))  # all overhead duration is at most 4

        max_hwaas = min(max_hwaas, a121.SubsweepConfig.MAX_HWAAS)

        return max_hwaas

    @classmethod
    def _get_step_length(cls, profile: a121.Profile) -> int:
        """
        Returns a minimal step length in order to achieve independent points,
        based on profile.
        """
        return cls.DEFAULT_STEP_LENGTH[profile]

    @classmethod
    def _get_sensor_config(cls, config: DetectorConfig) -> a121.SensorConfig:
        start_m = config.start_point * APPROX_BASE_STEP_LENGTH_M

        if config.profile is not None:
            profile = config.profile
        else:
            # Take the highest possible profile
            viable_profiles = [k for k, v in cls.MIN_DIST_M.items() if v is None or v <= start_m]
            profile = viable_profiles[-1]

        if config.sweep_rate is not None:
            sweep_rate = config.sweep_rate
        else:
            sweep_rate = config._get_min_sweep_rate(config.max_speed)

        frame_rate = config.frame_rate  # This can be none

        if config.step_length is not None:
            step_length = config.step_length
        else:
            step_length = cls._get_step_length(profile)

        end_point = config.start_point + (config.num_points - 1) * step_length
        prf = select_prf(end_point, profile)

        if config.hwaas is not None:
            hwaas = config.hwaas
        else:
            max_hwaas = cls._get_max_hwaas(sweep_rate, config.num_points, prf, profile)
            hwaas = max(int(max_hwaas * 0.9), 1)

        sensor_config = a121.SensorConfig(
            profile=profile,
            start_point=config.start_point,
            num_points=config.num_points,
            step_length=step_length,
            prf=prf,
            hwaas=hwaas,
            sweeps_per_frame=NUM_SEGMENTS * config.num_bins,
            sweep_rate=sweep_rate,
            frame_rate=frame_rate,
            inter_frame_idle_state=a121.IdleState.READY,
            double_buffering=False,
            continuous_sweep_mode=False,
        )
        return sensor_config

    @classmethod
    def _get_processor_config(cls, config: DetectorConfig) -> ProcessorConfig:
        ret_config = ProcessorConfig(threshold=config.threshold, num_segments=NUM_SEGMENTS)
        return ret_config

    def get_next(self) -> DetectorResult:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        extra_result = DetectorExtraResult(
            psd=processor_result.extra_result.psd,
            velocities=processor_result.extra_result.velocities,
            actual_thresholds=processor_result.extra_result.actual_thresholds,
        )

        detector_result = DetectorResult(
            extra_result=extra_result,
            speed_per_depth=processor_result.speed_per_depth,
        )
        return detector_result

    def update_config(self, config: DetectorConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        recorder_result = self.client.stop_session()
        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()
        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    config: DetectorConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "detector_config", config.to_json())


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, DetectorConfig]:
    sensor_id = algo_group["sensor_id"][()]
    config = DetectorConfig.from_json(algo_group["detector_config"][()])
    return sensor_id, config
