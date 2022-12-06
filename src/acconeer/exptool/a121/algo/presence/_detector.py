# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
from attr import Attribute

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import Result
from acconeer.exptool.a121._core.entities.configs.config_enums import IdleState, Profile
from acconeer.exptool.a121._core.utils import is_divisor_of, is_multiple_of
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import ENVELOPE_FWHM_M, AlgoConfigBase, select_prf

from ._processors import Processor, ProcessorConfig, ProcessorContext, ProcessorExtraResult


SPARSE_IQ_PPC = 24


def optional_profile_converter(profile: Optional[Profile]) -> Optional[Profile]:
    if profile is None:
        return None

    return Profile(profile)


def idle_state_converter(idle_state: IdleState) -> IdleState:
    return IdleState(idle_state)


@attrs.mutable(kw_only=True)
class DetectorConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=1.0)
    """Start point of measurement interval in meters."""

    end_m: float = attrs.field(default=2.0)
    """End point of measurement interval in meters."""

    profile: Optional[a121.Profile] = attrs.field(
        default=None, converter=optional_profile_converter
    )
    """
    Sets the profile. If no argument is provided, the highest possible
    profile without interference of direct leakage is used to maximize SNR.
    """

    step_length: Optional[int] = attrs.field(default=None)
    """
    Step length in points. If no argument is provided, the step length is automatically
    calculated based on the profile.
    """

    frame_rate: float = attrs.field(default=10.0)
    """Frame rate in Hz."""

    sweeps_per_frame: int = attrs.field(default=16)
    """Number of sweeps per frame."""

    hwaas: int = attrs.field(default=32)
    """Number of HWAAS."""

    inter_frame_idle_state: a121.IdleState = attrs.field(
        default=a121.IdleState.DEEP_SLEEP, converter=idle_state_converter
    )
    """Sets the inter frame idle state."""

    intra_enable: bool = attrs.field(default=True)
    """
    Enables the intra-frame presence detection used for detecting
    faster movements inside frames.
    """

    intra_detection_threshold: float = attrs.field(default=1.3)
    """Detection threshold for the intra-frame presence detection."""

    intra_frame_time_const: float = attrs.field(default=0.15)
    """Time constant for the depthwise filtering in the intra-frame part."""

    intra_output_time_const: float = attrs.field(default=0.5)
    """Time constant for the output in the intra-frame part."""

    inter_enable: bool = attrs.field(default=True)
    """
    Enables the inter-frame presence detection used for detecting
    slower movements between frames
    """

    inter_detection_threshold: float = attrs.field(default=1)
    """Detection threshold for the inter-frame presence detection."""

    inter_frame_fast_cutoff: float = attrs.field(default=20.0)
    """
    Cutoff frequency of the low pass filter for the fast filtered absolute sweep mean.
    No filtering is applied if the cutoff is set over half the frame rate (Nyquist limit).
    """

    inter_frame_slow_cutoff: float = attrs.field(default=0.2)
    """Cutoff frequency of the low pass filter for the slow filtered absolute sweep mean."""

    inter_frame_deviation_time_const: float = attrs.field(default=0.5)
    """Time constant of the low pass filter for the inter-frame deviation between fast and slow."""

    inter_output_time_const: float = attrs.field(default=5)
    """Time constant for the output in the inter-frame part."""

    inter_phase_boost: bool = attrs.field(default=False)
    """Enables the inter-frame phase boost. Used to increase slow motion detection."""

    inter_frame_presence_timeout: Optional[int] = attrs.field(default=None)
    """
    Number of seconds the inter-frame presence score needs to decrease before exponential
    scaling starts for faster decline.
    """

    @step_length.validator
    def _validate_step_length(self, attrs: Attribute, step_length: int) -> None:
        if step_length is not None:
            if not (
                is_divisor_of(SPARSE_IQ_PPC, step_length)
                or is_multiple_of(SPARSE_IQ_PPC, step_length)
            ):
                raise ValueError(f"step_length must be a divisor or multiple of {SPARSE_IQ_PPC}")

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if self.sweeps_per_frame <= Processor.NOISE_ESTIMATION_DIFF_ORDER:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "sweeps_per_frame",
                    f"Must be greater than {Processor.NOISE_ESTIMATION_DIFF_ORDER}",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class DetectorResult:
    intra_presence_score: float = attrs.field()
    """A measure of the amount of fast motion detected."""

    inter_presence_score: float = attrs.field()
    """A measure of the amount of slow motion detected"""

    presence_distance: float = attrs.field()
    """The distance, in meters, to the detected object"""

    presence_detected: bool = attrs.field()
    """True if presence was detected, False otherwise"""

    processor_extra_result: ProcessorExtraResult = attrs.field()
    service_result: a121.Result = attrs.field()


class Detector:
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
        client: a121.ClientBase,
        sensor_id: int,
        detector_config: DetectorConfig,
    ) -> None:
        self.client = client
        self.sensor_id = sensor_id
        self.detector_config = detector_config

        self.started = False

    def _estimate_frame_rate(self) -> float:
        delta_times = np.full(2, np.nan)

        self.client.setup_session(self.session_config)
        self.client.start_session()

        for i in range(4):
            result = self.client.get_next()
            assert isinstance(result, Result)

            if i < 2:
                last_time = result.tick_time
                continue

            time = result.tick_time
            delta = time - last_time
            last_time = time
            delta_times = np.roll(delta_times, -1)
            delta_times[-1] = delta

        self.client.stop_session()

        return float(1.0 / np.nanmean(delta_times))

    def start(self, recorder: Optional[a121.Recorder] = None) -> None:
        if self.started:
            raise RuntimeError("Already started")

        sensor_config = self._get_sensor_config(self.detector_config)
        self.session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        estimated_frame_rate = self._estimate_frame_rate()
        # Add estimated frame rate to context if it differs more than 10% from the set frame rate
        if (
            np.abs(self.detector_config.frame_rate - estimated_frame_rate)
            / self.detector_config.frame_rate
            > 0.1
        ):
            context = ProcessorContext(estimated_frame_rate=estimated_frame_rate)
        else:
            context = ProcessorContext(estimated_frame_rate=None)

        metadata = self.client.setup_session(self.session_config)
        assert isinstance(metadata, a121.Metadata)

        processor_config = self._get_processor_config(self.detector_config)

        self.processor = Processor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            context=context,
        )

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("presence_detector")
                _record_algo_data(
                    algo_group,
                    self.sensor_id,
                    self.detector_config,
                )
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        self.client.start_session(recorder)

        self.started = True

    @classmethod
    def _get_sensor_config(cls, detector_config: DetectorConfig) -> a121.SensorConfig:
        start_point = int(np.floor(detector_config.start_m / Processor.APPROX_BASE_STEP_LENGTH_M))
        if detector_config.profile is not None:
            profile = detector_config.profile
        else:
            viable_profiles = [
                k for k, v in cls.MIN_DIST_M.items() if v is None or v <= detector_config.start_m
            ]
            profile = viable_profiles[-1]

        if detector_config.step_length is not None:
            step_length = detector_config.step_length
        else:
            # Calculate biggest possible step length based on the fwhm of the set profile
            # Achieve detection on the complete range with minimum number of sampling points
            fwhm_p = Processor.ENVELOPE_FWHM_M[profile] / Processor.APPROX_BASE_STEP_LENGTH_M
            if fwhm_p < SPARSE_IQ_PPC:
                step_length = SPARSE_IQ_PPC // int(np.ceil(SPARSE_IQ_PPC / fwhm_p))
            else:
                step_length = int((fwhm_p // SPARSE_IQ_PPC) * SPARSE_IQ_PPC)

        num_point = int(
            np.ceil(
                (detector_config.end_m - detector_config.start_m)
                / (step_length * Processor.APPROX_BASE_STEP_LENGTH_M)
            )
            + 1
        )
        end_point = start_point + (num_point - 1) * step_length
        return a121.SensorConfig(
            profile=profile,
            start_point=start_point,
            num_points=num_point,
            step_length=step_length,
            prf=select_prf(end_point, profile),
            hwaas=detector_config.hwaas,
            sweeps_per_frame=detector_config.sweeps_per_frame,
            frame_rate=detector_config.frame_rate,
            inter_frame_idle_state=detector_config.inter_frame_idle_state,
        )

    @classmethod
    def _get_processor_config(cls, detector_config: DetectorConfig) -> ProcessorConfig:
        return ProcessorConfig(
            intra_enable=detector_config.intra_enable,
            intra_detection_threshold=detector_config.intra_detection_threshold,
            intra_frame_time_const=detector_config.intra_frame_time_const,
            intra_output_time_const=detector_config.intra_output_time_const,
            inter_enable=detector_config.inter_enable,
            inter_detection_threshold=detector_config.inter_detection_threshold,
            inter_frame_fast_cutoff=detector_config.inter_frame_fast_cutoff,
            inter_frame_slow_cutoff=detector_config.inter_frame_slow_cutoff,
            inter_frame_deviation_time_const=detector_config.inter_frame_deviation_time_const,
            inter_output_time_const=detector_config.inter_output_time_const,
            inter_phase_boost=detector_config.inter_phase_boost,
            inter_frame_presence_timeout=detector_config.inter_frame_presence_timeout,
        )

    def get_next(self) -> DetectorResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return DetectorResult(
            intra_presence_score=processor_result.intra_presence_score,
            inter_presence_score=processor_result.inter_presence_score,
            presence_distance=processor_result.presence_distance,
            presence_detected=processor_result.presence_detected,
            processor_extra_result=processor_result.extra_result,
            service_result=result,
        )

    def update_config(self, config: DetectorConfig) -> None:
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
    detector_config: DetectorConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )
    _create_h5_string_dataset(algo_group, "detector_config", detector_config.to_json())


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, DetectorConfig]:
    sensor_id = algo_group["sensor_id"][()]
    config = DetectorConfig.from_json(algo_group["detector_config"][()])
    return sensor_id, config
